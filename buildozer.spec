[app]
title = SOS69069 24H
package.name = sos6906924h
package.domain = org.sos69069
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt,md
source.main = main.py
version = 1.1.0
android.numeric_version = 110

# Force the same Python the working app used (3.11)
requirements = hostpython3==3.11.9,python3==3.11.9,kivy,requests==2.31.0,urllib3==2.0.7,certifi,chardet,idna,charset-normalizer==3.3.2

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
