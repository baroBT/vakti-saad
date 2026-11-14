[app]
title = Vakt-i Saad
package.name = vakti_saad
package.domain = org.barobt
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 0.1
requirements = python3,kivy,plyer
orientation = portrait
fullscreen = 0
icon.filename = icon.png
android.archs = arm64-v8a
android.accept_sdk_license = True
android.permissions = INTERNET,POST_NOTIFICATIONS
android.api = 31
android.minapi = 21
android.enable_androidx = True
android.release_artifact = apk

[buildozer]
log_level = 2
warn_on_root = 1
