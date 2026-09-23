[app]

title = SOS69069 24H
package.name = sos6906924h
package.domain = org.sos69069

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
source.exclude_dirs = tests, bin, venv, .git

version = 1.1.0

requirements = python3,kivy,web3,eth-account,eth-abi,eth-utils,hexbytes,cython,requests,urllib3,charset-normalizer,idna,certifi,pycryptodome

icon.filename = %(source.dir)s/icon.png

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,WAKE_LOCK,FOREGROUND_SERVICE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.build_tools = 34.0.0
android.enable_androidx = True
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True
android.logcat_filters = *:S python:D
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
