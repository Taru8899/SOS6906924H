#!/usr/bin/env python3
"""
SOS69069 24H Miner – pure Python (no web3 / eth-account)
Uses pure_crypto + requests so it builds cleanly with python-for-android.
"""

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.checkbox import CheckBox
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import Image
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import platform
from kivy.storage.jsonstore import JsonStore
import threading
import time
import hashlib
from datetime import datetime

# Pure-Python helpers from the working project
from pure_crypto import keccak256, sign as ecdsa_sign, privkey_to_address
import requests

CONTRACT = "0x7373DBC24Dcd785896E8Ac3d5372c6ced9B75a8A"
DEFAULT_INTENDED = "0x1C10e6574ee696f54b21A611a21313E4714628ad"
DEFAULT_RPC = "https://ethereum-rpc.publicnode.com"
DEFAULT_GAS_MAX = "0.4"
STORE = "sos24h_task.json"
CHAIN_ID = 1


def to_bytes(hexstr):
    hexstr = hexstr[2:] if hexstr.startswith("0x") else hexstr
    return bytes.fromhex(hexstr)


def encode_uint256(n):
    return n.to_bytes(32, "big")


def encode_address(addr):
    return bytes.fromhex(addr[2:].lower().zfill(40)).rjust(32, b"\x00")


def encode_bytes32(b):
    return b.ljust(32, b"\x00")[:32]


class PasswordPopup(Popup):
    def __init__(self, on_success, mode="unlock", **kwargs):
        super().__init__(title="Password", size_hint=(0.85, 0.4), **kwargs)
        self.on_success = on_success
        layout = BoxLayout(orientation="vertical", padding=12, spacing=8)
        self.pwd = TextInput(hint_text="Password", password=True, multiline=False)
        layout.add_widget(self.pwd)
        if mode == "set":
            self.pwd2 = TextInput(hint_text="Confirm", password=True, multiline=False)
            layout.add_widget(self.pwd2)
            btn = Button(text="Save & Protect", background_color=(0.1, 0.7, 0.3, 1))
        else:
            self.pwd2 = None
            btn = Button(text="Unlock", background_color=(0.1, 0.7, 0.3, 1))
        btn.bind(on_press=lambda x: self._ok(mode))
        layout.add_widget(btn)
        self.content = layout

    def _ok(self, mode):
        p1 = self.pwd.text.strip()
        if mode == "set" and (not p1 or p1 != self.pwd2.text.strip()):
            return
        self.dismiss()
        self.on_success(p1)


class MinerUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=8, spacing=6, **kwargs)
        Window.clearcolor = (0.07, 0.07, 0.10, 1)
        self.mining = False
        self.thread = None
        self.password = None
        self.store = JsonStore(STORE)
        self.total_spent = 0.0
        self.total_sigs = 0

        # Top bar
        top = BoxLayout(size_hint_y=None, height=52, spacing=8)
        try:
            top.add_widget(Image(source="icon.png", size_hint=(None, None), size=(44, 44)))
        except Exception:
            pass
        top.add_widget(Label(text="SOS69069 24H", font_size=20, bold=True))
        self.add_widget(top)

        self.add_widget(Label(text="Private Key", size_hint_y=None, height=20))
        self.pk = TextInput(hint_text="0x...", password=True, multiline=False, size_hint_y=None, height=40)
        self.add_widget(self.pk)

        self.add_widget(Label(text="IntendedTo", size_hint_y=None, height=20))
        self.target = TextInput(text=DEFAULT_INTENDED, multiline=False, size_hint_y=None, height=40)
        self.add_widget(self.target)

        self.add_widget(Label(text="RPC URL", size_hint_y=None, height=20))
        self.rpc = TextInput(text=DEFAULT_RPC, multiline=False, size_hint_y=None, height=40)
        self.add_widget(self.rpc)

        gas_row = BoxLayout(size_hint_y=None, height=40, spacing=6)
        self.gas = TextInput(text=DEFAULT_GAS_MAX, hint_text="Gas max gwei", size_hint_x=0.4)
        gas_row.add_widget(self.gas)
        self.save_gas = CheckBox(size_hint_x=None, width=30)
        gas_row.add_widget(self.save_gas)
        gas_row.add_widget(Label(text="Save gas for task", size_hint_x=0.5))
        self.add_widget(gas_row)

        btn_row = BoxLayout(size_hint_y=None, height=46, spacing=8)
        self.start_btn = Button(text="START / CONTINUE", background_color=(0.1, 0.7, 0.3, 1))
        self.start_btn.bind(on_press=self.on_start)
        self.stop_btn = Button(text="STOP", background_color=(0.75, 0.2, 0.2, 1), disabled=True)
        self.stop_btn.bind(on_press=self.on_stop)
        btn_row.add_widget(self.start_btn)
        btn_row.add_widget(self.stop_btn)
        self.add_widget(btn_row)

        self.stats = Label(text="Push: - | Trust: - | Effective: -\nSpent: 0 ETH | Sigs: 0",
                           size_hint_y=None, height=50, halign="left")
        self.stats.bind(size=self.stats.setter("text_size"))
        self.add_widget(self.stats)

        self.log_label = Label(text="Ready.\n", size_hint_y=None, height=200, halign="left", valign="top")
        self.log_label.bind(size=self.log_label.setter("text_size"))
        sc = ScrollView()
        sc.add_widget(self.log_label)
        self.add_widget(sc)

        Clock.schedule_once(self.try_load, 0.4)
        if platform == "android":
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.INTERNET, Permission.WAKE_LOCK])
            except Exception:
                pass

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_label.text = f"[{ts}] {msg}\n" + self.log_label.text[:1600]

    def try_load(self, dt):
        if self.store.exists("task"):
            self.log("Saved task found – enter password to unlock")
            PasswordPopup(on_success=self.unlock, mode="unlock").open()

    def unlock(self, pwd):
        try:
            d = self.store.get("task")
            if d.get("pwd_hash") == hashlib.sha256(pwd.encode()).hexdigest():
                self.password = pwd
                self.pk.text = d.get("pk", "")
                self.target.text = d.get("intended", DEFAULT_INTENDED)
                self.rpc.text = d.get("rpc", DEFAULT_RPC)
                self.gas.text = d.get("gas_max", DEFAULT_GAS_MAX)
                self.total_spent = d.get("spent", 0.0)
                self.total_sigs = d.get("sigs", 0)
                self.log("Task unlocked")
            else:
                self.log("Wrong password")
        except Exception as e:
            self.log(f"Load error: {e}")

    def save(self, pwd):
        self.store.put("task",
            pwd_hash=hashlib.sha256(pwd.encode()).hexdigest(),
            pk=self.pk.text.strip(),
            intended=self.target.text.strip(),
            rpc=self.rpc.text.strip(),
            gas_max=self.gas.text.strip(),
            spent=self.total_spent,
            sigs=self.total_sigs)
        self.password = pwd

    def on_start(self, *_):
        pk = self.pk.text.strip()
        if not pk.startswith("0x") or len(pk) < 60:
            self.log("Invalid private key")
            return
        if not self.password:
            PasswordPopup(on_success=self._after_pwd, mode="set").open()
        else:
            self._go()

    def _after_pwd(self, pwd):
        self.save(pwd)
        self._go()

    def _go(self):
        self.mining = True
        self.start_btn.disabled = True
        self.stop_btn.disabled = False
        self.log("Mining 6→9→pause 6s ...")
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def on_stop(self, *_):
        self.mining = False
        self.start_btn.disabled = False
        self.stop_btn.disabled = True
        self.log("Stopping...")
        if self.password:
            self.save(self.password)

    def rpc_call(self, method, params):
        url = self.rpc.text.strip() or DEFAULT_RPC
        r = requests.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=25)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise Exception(data["error"])
        return data["result"]

    def loop(self):
        try:
            pk_hex = self.pk.text.strip()
            priv = to_bytes(pk_hex)
            signer = privkey_to_address(priv)
            target = self.target.text.strip()
            self.log(f"Signer {signer[:10]}...")

            while self.mining:
                try:
                    for batch_size in (6, 9):
                        if not self.mining:
                            break
                        # Build unique payloads + sign (simplified EIP-712 style hash)
                        # For full production use the pure_crypto + proper typed-data encoding
                        # from the working project. This is a minimal runnable skeleton.
                        self.log(f"Batch {batch_size} (skeleton – integrate full typed data next)")
                        time.sleep(2)  # placeholder until full tx builder is wired
                        self.total_sigs += batch_size
                        Clock.schedule_once(lambda dt: self._upd(), 0)
                    self.log("Pause 6s")
                    time.sleep(6)
                except Exception as e:
                    self.log(f"Err: {str(e)[:60]}")
                    time.sleep(10)
        except Exception as e:
            self.log(f"Fatal: {e}")
        finally:
            self.mining = False
            Clock.schedule_once(lambda dt: self.on_stop(), 0)

    def _upd(self):
        self.stats.text = f"Push: - | Trust: - | Effective: -\nSpent: {self.total_spent:.5f} ETH | Sigs: {self.total_sigs}"
        if self.password:
            self.save(self.password)


class SOS69069App(App):
    def build(self):
        return MinerUI()


if __name__ == "__main__":
    SOS69069App().run()
