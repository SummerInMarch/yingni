package com.yingni.app;

import android.app.Activity;
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
    private String pendingPicture;
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

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == 41 && fileCallback != null) {
            fileCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data));
            fileCallback = null;
        }
        if (requestCode == 42) {
            String picture = pendingPicture, token = pendingToken;
            pendingPicture = null; pendingToken = null;
            if (resultCode == RESULT_OK && data != null && data.getData() != null && picture != null && token != null) {
                Uri destination = data.getData();
                new Thread(() -> savePicture(destination, picture, token)).start();
            }
        }
    }

    private class NativeBridge {
        @JavascriptInterface public void savePicture(String picture, String token, String mime) {
            if (picture == null || token == null || !picture.matches("[a-f0-9]{32}") || !token.matches("[A-Za-z0-9_-]{30,100}") || !("image/jpeg".equals(mime) || "image/png".equals(mime))) return;
            runOnUiThread(() -> {
                pendingPicture = picture; pendingToken = token;
                Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType(mime);
                intent.putExtra(Intent.EXTRA_TITLE, "yingni-" + picture.substring(0, 8) + ("image/jpeg".equals(mime) ? ".jpg" : ".png"));
                try { startActivityForResult(intent, 42); }
                catch (Exception e) { pendingPicture = null; pendingToken = null; Toast.makeText(MainActivity.this, "无法打开保存位置", Toast.LENGTH_SHORT).show(); }
            });
        }
    }

    private void savePicture(Uri destination, String picture, String token) {
        HttpURLConnection connection = null;
        boolean success = false;
        try {
            connection = (HttpURLConnection) new URL(HOME + "picture/" + picture).openConnection();
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
        runOnUiThread(() -> Toast.makeText(this, saved ? "图片已保存" : "图片保存失败，请重试", Toast.LENGTH_SHORT).show());
    }

    @Override public void onBackPressed() {
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }
}
