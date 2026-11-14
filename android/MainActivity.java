package com.yingni.app;

import android.app.Activity;
import android.Manifest;
import android.content.pm.PackageManager;
import android.webkit.PermissionRequest;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.ValueCallback;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import org.json.JSONObject;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import android.widget.Toast;

/** 承载映你界面，并使用系统选择器上传参考图。 */
public class MainActivity extends Activity {
    private static final String HOME = "https://home.samoyeai.com/yingni/";
    private static final String SETUP_TOKEN = "__SETUP_TOKEN__";
    private WebView web;
    private ValueCallback<Uri[]> fileCallback;
    private PermissionRequest microphoneRequest;
    private boolean nativeMicrophoneRequest;
    private String pendingPath;
    private String pendingToken;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.addJavascriptInterface(new NativeBridge(), "Yingni");
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                return !"https".equals(uri.getScheme()) || !"home.samoyeai.com".equals(uri.getHost()) || !uri.getPath().startsWith("/yingni/");
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (url.startsWith(HOME)) view.evaluateJavascript("window.YINGNI_SETUP_TOKEN=" + JSONObject.quote(SETUP_TOKEN), null);
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public void onPermissionRequest(PermissionRequest request) {
                runOnUiThread(() -> {
                    Uri origin = request.getOrigin();
                    String[] resources = request.getResources();
                    boolean requestsAudio = false;
                    for (String resource : resources) {
                        if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(resource)) requestsAudio = true;
                    }
                    if (!"https".equals(origin.getScheme()) || !"home.samoyeai.com".equals(origin.getHost()) ||
                            !requestsAudio || microphoneRequest != null) {
                        request.deny(); return;
                    }
                    if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                        request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE}); return;
                    }
                    microphoneRequest = request;
                    requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 43);
                });
            }
            @Override public void onPermissionRequestCanceled(PermissionRequest request) {
                runOnUiThread(() -> { if (microphoneRequest == request) microphoneRequest = null; });
            }
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                try { startActivityForResult(params.createIntent(), 41); return true; }
                catch (Exception e) { fileCallback = null; callback.onReceiveValue(null); return false; }
            }
        });
        setContentView(web);
        web.loadUrl(HOME);
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == 44 && nativeMicrophoneRequest) {
            nativeMicrophoneRequest = false;
            boolean granted = results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED;
            web.evaluateJavascript("window.yingniMicrophoneResult(" + granted + ")", null);
        }
        if (requestCode == 43 && microphoneRequest != null) {
            PermissionRequest request = microphoneRequest; microphoneRequest = null;
            if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
            else request.deny();
        }
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == 41 && fileCallback != null) {
            fileCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data));
            fileCallback = null;
        }
        if (requestCode == 42) {
            String path = pendingPath, token = pendingToken;
            pendingPath = null; pendingToken = null;
            if (resultCode == RESULT_OK && data != null && data.getData() != null && path != null && token != null) {
                Uri destination = data.getData();
                new Thread(() -> saveFile(destination, path, token)).start();
            }
        }
    }

    private class NativeBridge {
        @JavascriptInterface public void requestMicrophone() {
            runOnUiThread(() -> {
                if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                    web.evaluateJavascript("window.yingniMicrophoneResult(true)", null);
                } else if (!nativeMicrophoneRequest) {
                    nativeMicrophoneRequest = true;
                    requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 44);
                }
            });
        }
        @JavascriptInterface public void savePicture(String picture, String token, String mime) {
            if (picture == null || token == null || !picture.matches("[a-f0-9]{32}") || !token.matches("[A-Za-z0-9_-]{30,100}") || !("image/jpeg".equals(mime) || "image/png".equals(mime))) return;
            chooseDestination("picture/" + picture, token, mime, "yingni-" + picture.substring(0, 8) + ("image/jpeg".equals(mime) ? ".jpg" : ".png"));
        }

        @JavascriptInterface public void saveDocument(String id, String token, String name, String mime) {
            if (id == null || token == null || name == null || mime == null || !id.matches("[a-f0-9]{32}") || !token.matches("[A-Za-z0-9_-]{30,100}") || name.length() > 160 || !mime.matches("text/plain|application/pdf|application/vnd\\.openxmlformats-officedocument\\.wordprocessingml\\.document")) return;
            String safeName = name.replaceAll("[/\\\\\\p{Cntrl}]", "_");
            chooseDestination("files/" + id, token, mime, safeName);
        }

        private void chooseDestination(String path, String token, String mime, String name) {
            runOnUiThread(() -> {
                pendingPath = path; pendingToken = token;
                Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType(mime);
                intent.putExtra(Intent.EXTRA_TITLE, name);
                try { startActivityForResult(intent, 42); }
                catch (Exception e) { pendingPath = null; pendingToken = null; Toast.makeText(MainActivity.this, "无法打开保存位置", Toast.LENGTH_SHORT).show(); }
            });
        }
    }

    private void saveFile(Uri destination, String path, String token) {
        HttpURLConnection connection = null;
        boolean success = false;
        try {
            connection = (HttpURLConnection) new URL(HOME + path).openConnection();
            connection.setRequestProperty("Authorization", "Bearer " + token);
            connection.setConnectTimeout(15000); connection.setReadTimeout(60000);
            if (connection.getResponseCode() != 200) throw new java.io.IOException("download failed");
            try (InputStream input = connection.getInputStream(); OutputStream output = getContentResolver().openOutputStream(destination)) {
                if (output == null) throw new java.io.IOException("cannot open destination");
                byte[] buffer = new byte[8192]; int n; long total = 0;
                while ((n = input.read(buffer)) != -1) {
                    total += n; if (total > 30L * 1024 * 1024) throw new java.io.IOException("image too large");
                    output.write(buffer, 0, n);
                }
            }
            success = true;
        } catch (Exception ignored) { }
        finally { if (connection != null) connection.disconnect(); }
        final boolean saved = success;
        runOnUiThread(() -> Toast.makeText(this, saved ? "已保存" : "保存失败，请重试", Toast.LENGTH_SHORT).show());
    }

    @Override public void onBackPressed() {
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }
}
