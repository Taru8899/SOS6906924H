[app]
title = SOS69069 24H
package.name = sos6906924h
package.domain = org.sos69069
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt,md
source.main = main.py
version = 1.1.0
android.numeric_version = 110

# Force Python 3.11 (critical) + same simple deps as the working app
requirements = hostpython3==3.11.9,python3==3.11.9,kivy,requests,urllib3,certifi,chardet,idna

orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/icon.png

android.archs = arm64-v8a
android.permissions = INTERNET,WAKE_LOCK
android.allow_backup = True
android.api = 33
android.minapi = 24
android.ndk = 25b
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
