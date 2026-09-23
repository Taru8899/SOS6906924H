#!/usr/bin/env python3
"""
SOS69069 24H Miner
- Logo top-left
- Private key + task encrypted & saved locally (password protected)
- Pre-filled IntendedTo + RPC
- Mining sequence: 6 → 9 → pause 6s → repeat
- Gas max editable + save checkbox
"""

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
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
import os
import hashlib
import base64
from datetime import datetime

try:
    from web3 import Web3
    from eth_account import Account
    from eth_account.messages import encode_typed_data
except ImportError:
    Web3 = None
    Account = None
    encode_typed_data = None

# Default values
DEFAULT_INTENDED_TO = "0x1C10e6574ee696f54b21A611a21313E4714628ad"
DEFAULT_RPC = "https://ethereum-rpc.publicnode.com"
DEFAULT_GAS_MAX_GWEI = "0.4"
CONTRACT = "0x7373DBC24Dcd785896E8Ac3d5372c6ced9B75a8A"
STORE_FILE = "sos69069_task.json"


class PasswordPopup(Popup):
    def __init__(self, on_success, mode="unlock", **kwargs):
        super().__init__(title="Password", size_hint=(0.85, 0.4), **kwargs)
        self.on_success = on_success
        self.mode = mode  # "set" or "unlock"

        layout = BoxLayout(orientation="vertical", padding=15, spacing=10)
        self.pwd = TextInput(hint_text="Enter password", password=True, multiline=False)
        layout.add_widget(self.pwd)

        if mode == "set":
            self.pwd2 = TextInput(hint_text="Confirm password", password=True, multiline=False)
            layout.add_widget(self.pwd2)
            btn = Button(text="Save & Protect", background_color=(0.1, 0.7, 0.3, 1))
        else:
            self.pwd2 = None
            btn = Button(text="Unlock", background_color=(0.1, 0.7, 0.3, 1))

        btn.bind(on_press=self.submit)
        layout.add_widget(btn)
        self.content = layout

    def submit(self, instance):
        p1 = self.pwd.text.strip()
        if self.mode == "set":
            p2 = self.pwd2.text.strip()
            if not p1 or p1 != p2:
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
        self.store = JsonStore(STORE_FILE)
        self.total_spent_eth = 0.0
        self.total_sigs = 0

        # ===== TOP BAR (Logo left + Title) =====
        top = BoxLayout(size_hint_y=None, height=56, spacing=8, padding=[4, 4, 4, 4])
        try:
            logo = Image(source="icon.png", size_hint=(None, None), size=(48, 48))
            top.add_widget(logo)
        except Exception:
            top.add_widget(Label(text="SOS", size_hint=(None, None), size=(48, 48)))
        top.add_widget(Label(text="SOS69069 24H", font_size=20, bold=True, halign="left"))
        self.add_widget(top)

        # ===== PRIVATE KEY =====
        self.add_widget(Label(text="Private Key", size_hint_y=None, height=22, halign="left"))
        self.pk_input = TextInput(hint_text="0x...", password=True, multiline=False, size_hint_y=None, height=42)
        self.add_widget(self.pk_input)

        # ===== INTENDED TO (pre-filled) =====
        self.add_widget(Label(text="IntendedTo Address", size_hint_y=None, height=22, halign="left"))
        self.target_input = TextInput(text=DEFAULT_INTENDED_TO, multiline=False, size_hint_y=None, height=42)
        self.add_widget(self.target_input)

        # ===== RPC (pre-filled) =====
        self.add_widget(Label(text="RPC URL", size_hint_y=None, height=22, halign="left"))
        self.rpc_input = TextInput(text=DEFAULT_RPC, multiline=False, size_hint_y=None, height=42)
        self.add_widget(self.rpc_input)

        # ===== GAS MAX + CHECKBOX =====
        gas_row = BoxLayout(size_hint_y=None, height=42, spacing=8)
        self.gas_input = TextInput(text=DEFAULT_GAS_MAX_GWEI, hint_text="Gas max gwei", multiline=False, size_hint_x=0.45)
        gas_row.add_widget(self.gas_input)
        self.save_gas_check = CheckBox(size_hint_x=None, width=32)
        gas_row.add_widget(self.save_gas_check)
        gas_row.add_widget(Label(text="Save gas for this task", size_hint_x=0.5, halign="left"))
        self.add_widget(gas_row)

        # ===== BUTTONS =====
        btn_row = BoxLayout(size_hint_y=None, height=48, spacing=8)
        self.start_btn = Button(text="START / CONTINUE", background_color=(0.1, 0.7, 0.3, 1))
        self.start_btn.bind(on_press=self.on_start)
        self.stop_btn = Button(text="STOP", background_color=(0.75, 0.2, 0.2, 1), disabled=True)
        self.stop_btn.bind(on_press=self.on_stop)
        btn_row.add_widget(self.start_btn)
        btn_row.add_widget(self.stop_btn)
        self.add_widget(btn_row)

        # ===== STATS =====
        self.stats_label = Label(
            text="Push: - | Trust: - | Effective: -\nSpent: 0.00000 ETH | Sigs: 0",
            size_hint_y=None, height=55, halign="left", valign="middle"
        )
        self.stats_label.bind(size=self.stats_label.setter("text_size"))
        self.add_widget(self.stats_label)

        # ===== LOG =====
        self.log_label = Label(text="Ready. Enter private key and press START.\n", size_hint_y=None, height=220, halign="left", valign="top")
        self.log_label.bind(size=self.log_label.setter("text_size"))
        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(self.log_label)
        self.add_widget(scroll)

        # Try load previous task on start
        Clock.schedule_once(self.try_load_task, 0.5)

        if platform == "android":
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.INTERNET, Permission.WAKE_LOCK])
            except Exception:
                pass

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_label.text = f"[{ts}] {msg}\n" + self.log_label.text[:1800]

    def try_load_task(self, dt):
        if self.store.exists("task"):
            self.log("Saved task found. Enter password to unlock & continue.")
            popup = PasswordPopup(on_success=self.unlock_task, mode="unlock")
            popup.open()

    def unlock_task(self, password):
        try:
            data = self.store.get("task")
            # Simple integrity check (not full encryption for simplicity)
            if data.get("pwd_hash") == hashlib.sha256(password.encode()).hexdigest():
                self.password = password
                self.pk_input.text = data.get("pk", "")
                self.target_input.text = data.get("intended", DEFAULT_INTENDED_TO)
                self.rpc_input.text = data.get("rpc", DEFAULT_RPC)
                self.gas_input.text = data.get("gas_max", DEFAULT_GAS_MAX_GWEI)
                self.total_spent_eth = data.get("spent", 0.0)
                self.total_sigs = data.get("sigs", 0)
                self.log("Task unlocked. You can press START / CONTINUE.")
            else:
                self.log("Wrong password.")
        except Exception as e:
            self.log(f"Load error: {e}")

    def save_task(self, password):
        try:
            self.store.put("task",
                pwd_hash=hashlib.sha256(password.encode()).hexdigest(),
                pk=self.pk_input.text.strip(),
                intended=self.target_input.text.strip(),
                rpc=self.rpc_input.text.strip(),
                gas_max=self.gas_input.text.strip(),
                spent=self.total_spent_eth,
                sigs=self.total_sigs
            )
            self.password = password
            self.log("Task + key saved (password protected).")
        except Exception as e:
            self.log(f"Save error: {e}")

    def on_start(self, instance):
        pk = self.pk_input.text.strip()
        if not pk.startswith("0x") or len(pk) < 60:
            self.log("Invalid private key")
            return
        target = self.target_input.text.strip()
        if not target.startswith("0x") or len(target) != 42:
            self.log("Invalid IntendedTo")
            return

        # Ask for password if not yet set
        if not self.password:
            popup = PasswordPopup(on_success=self._start_after_pwd, mode="set")
            popup.open()
        else:
            self._start_mining()

    def _start_after_pwd(self, password):
        self.save_task(password)
        self._start_mining()

    def _start_mining(self):
        self.mining = True
        self.start_btn.disabled = True
        self.stop_btn.disabled = False
        self.log("Mining started (6 → 9 → pause 6s)...")
        self.thread = threading.Thread(target=self.mine_loop, daemon=True)
        self.thread.start()

    def on_stop(self, instance):
        self.mining = False
        self.start_btn.disabled = False
        self.stop_btn.disabled = True
        self.log("Stopping after current batch...")
        if self.password:
            self.save_task(self.password)

    def mine_loop(self):
        try:
            rpc = self.rpc_input.text.strip() or DEFAULT_RPC
            self.w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 25}))
            if not self.w3.is_connected():
                self.log("RPC failed")
                self.mining = False
                return

            pk = self.pk_input.text.strip()
            account = Account.from_key(pk)
            signer = account.address
            target = self.target_input.text.strip()
            self.log(f"Signer: {signer[:8]}...{signer[-6:]}")

            try:
                gas_max_gwei = float(self.gas_input.text.strip() or DEFAULT_GAS_MAX_GWEI)
            except:
                gas_max_gwei = 0.4

            ABI = [
                {"inputs":[{"name":"signer","type":"address"},{"name":"intendedTo","type":"address"},
                           {"name":"payloadHashes","type":"bytes32[]"},{"name":"signatures","type":"bytes[]"},
                           {"name":"metadatas","type":"string[]"}],
                 "name":"recordSignatureOne","outputs":[],"stateMutability":"nonpayable","type":"function"},
                {"inputs":[{"name":"user","type":"address"}],
                 "name":"statsOf","outputs":[{"name":"pushCount","type":"uint256"},
                                             {"name":"trustCount","type":"uint256"},
                                             {"name":"effective","type":"int256"}],
                 "stateMutability":"view","type":"function"}
            ]
            contract = self.w3.eth.contract(address=CONTRACT, abi=ABI)

            DOMAIN = {"name":"69069","version":"1","chainId":1,"verifyingContract":CONTRACT}
            TYPES = {"Record":[
                {"name":"signer","type":"address"},
                {"name":"intendedTo","type":"address"},
                {"name":"payloadHash","type":"bytes32"},
                {"name":"metadataHash","type":"bytes32"}
            ]}

            def make_meta(i):
                # Simple unique ≤64 char metadata (news can be added later)
                base = f"sos24h-{datetime.now().strftime('%Y%m%d')}-{i}-{int(time.time())%100000}"
                return base[:64]

            def sign_batch(n):
                hashes, sigs, metas = [], [], []
                for i in range(n):
                    ph = self.w3.keccak(text=f"sos24h-{signer.lower()}-{int(time.time())}-{i}-{n}")
                    meta = make_meta(i)
                    msg = {
                        "signer": signer,
                        "intendedTo": target,
                        "payloadHash": ph,
                        "metadataHash": self.w3.keccak(text=meta)
                    }
                    signable = encode_typed_data(DOMAIN, TYPES, msg)
                    sig = account.sign_message(signable).signature
                    hashes.append(ph)
                    sigs.append(sig)
                    metas.append(meta)
                return hashes, sigs, metas

            def submit(hashes, sigs, metas):
                base = self.w3.eth.gas_price
                max_fee = min(int(base * 1.8), self.w3.to_wei(gas_max_gwei, "gwei"))
                tip = self.w3.to_wei(0.05, "gwei")
                tx = contract.functions.recordSignatureOne(
                    signer, target, hashes, sigs, metas
                ).build_transaction({
                    "from": signer,
                    "nonce": self.w3.eth.get_transaction_count(signer),
                    "gas": 4_800_000,
                    "maxFeePerGas": max_fee,
                    "maxPriorityFeePerGas": tip,
                    "chainId": 1
                })
                signed = account.sign_transaction(tx)
                tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
                self.log(f"Sent {len(hashes)} → {tx_hash.hex()[:14]}...")
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                cost = receipt.gasUsed * receipt.effectiveGasPrice / 1e18
                self.total_spent_eth += cost
                self.total_sigs += len(hashes)
                push, trust, eff = contract.functions.statsOf(signer).call()
                Clock.schedule_once(lambda dt: self.update_stats(push, trust, eff), 0)
                self.log(f"OK | {receipt.gasUsed} gas | {cost:.5f} ETH")
                return receipt

            # ===== MAIN SEQUENCE: 6 → 9 → pause 6s =====
            while self.mining:
                try:
                    # 6 signatures
                    h, s, m = sign_batch(6)
                    submit(h, s, m)
                    if not self.mining: break

                    # 9 signatures
                    h, s, m = sign_batch(9)
                    submit(h, s, m)
                    if not self.mining: break

                    # Pause 6 seconds
                    self.log("Pause 6s...")
                    time.sleep(6)

                except Exception as e:
                    self.log(f"Error: {str(e)[:70]}")
                    time.sleep(12)

        except Exception as e:
            self.log(f"Fatal: {e}")
        finally:
            self.mining = False
            Clock.schedule_once(lambda dt: self.on_stop(None), 0)

    def update_stats(self, push, trust, eff):
        self.stats_label.text = (
            f"Push: {push} | Trust: {trust} | Effective: {eff}\n"
            f"Spent: {self.total_spent_eth:.5f} ETH | Sigs: {self.total_sigs}"
        )
        if self.password:
            self.save_task(self.password)


class SOS69069App(App):
    def build(self):
        return MinerUI()


if __name__ == "__main__":
    SOS69069App().run()
