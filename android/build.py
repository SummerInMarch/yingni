"""使用本机 Android SDK 构建个人测试 APK。"""
import os
import shutil
import subprocess
from pathlib import Path

project = Path(__file__).resolve().parent.parent
sdk = Path(os.environ.get('ANDROID_SDK_ROOT', r'E:\Android\Sdk'))
java_bin = shutil.which('javac')
if java_bin:
    os.environ['JAVA_HOME'] = str(Path(java_bin).resolve().parent.parent)
tools = sdk / 'build-tools' / '35.0.0'
android_jar = sdk / 'platforms' / 'android-35' / 'android.jar'
build = project / 'build' / 'android'
for folder in ('src/com/yingni/app', 'classes', 'dex'):
    (build / folder).mkdir(parents=True, exist_ok=True)
secret = (project / '.bootstrap').read_text(encoding='utf-8').strip()
if not secret.isalnum():
    raise ValueError('Invalid setup token')
java = (project / 'android' / 'MainActivity.java').read_text(encoding='utf-8').replace('__SETUP_TOKEN__', secret)
(build / 'src/com/yingni/app/MainActivity.java').write_text(java, encoding='utf-8')

def run(*args):
    subprocess.run([str(x) for x in args], check=True)

run('javac', '-encoding', 'UTF-8', '-source', '8', '-target', '8', '-classpath', android_jar, '-d', build / 'classes', build / 'src/com/yingni/app/MainActivity.java')
run('jar', 'cf', build / 'classes.jar', '-C', build / 'classes', '.')
run(tools / 'd8.bat', '--lib', android_jar, '--min-api', '23', '--output', build / 'dex', build / 'classes.jar')
raw, aligned = build / 'raw.apk', build / 'aligned.apk'
run(tools / 'aapt.exe', 'package', '-f', '-M', project / 'android/AndroidManifest.xml', '-S', project / 'android/res', '-I', android_jar, '-F', raw)
run('jar', 'uf', raw, '-C', build / 'dex', 'classes.dex')
run(tools / 'zipalign.exe', '-f', '4', raw, aligned)
keystore = Path.home() / '.android' / 'debug.keystore'
keystore.parent.mkdir(parents=True, exist_ok=True)
if not keystore.exists():
    run('keytool', '-genkeypair', '-keystore', keystore, '-storepass', 'android', '-keypass', 'android', '-alias', 'androiddebugkey', '-dname', 'CN=Android Debug,O=Android,C=US', '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000')
output = project / 'build' / '映你-个人测试版.apk'
run(tools / 'apksigner.bat', 'sign', '--ks', keystore, '--ks-key-alias', 'androiddebugkey', '--ks-pass', 'pass:android', '--key-pass', 'pass:android', '--out', output, aligned)
run(tools / 'apksigner.bat', 'verify', '--verbose', output)
print('APK:', output)
