[app]

title = SOS69069 24H
package.name = sos6906924h
package.domain = org.sos69069

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
source.exclude_dirs = tests, bin, venv, .git

version = 1.1.0

requirements = hostpython3==3.11.16,python3==3.11.16,kivy==2.3.0,web3,eth-account,eth-abi,eth-utils,hexbytes,requests,urllib3,charset-normalizer,idna,certifi,pycryptodome,cython==0.29.36,pyjnius,android

icon.filename = %(source.dir)s/icon.png

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,WAKE_LOCK,FOREGROUND_SERVICE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.build_tools = 34.0.0
android.enable_androidx = True
android.archs = arm64-v8a
android.allow_backup = True
android.logcat_filters = *:S python:D
android.accept_sdk_license = True

p4a.branch = develop
p4a.bootstrap = sdl2
p4a.python_version = 3.11

[buildozer]
log_level = 2
warn_on_root = 1
