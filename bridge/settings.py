import base64
import ctypes
import json
import os
import pathlib
from ctypes import wintypes
from .core import BridgeError, atomic_write, dumps, detect_game

DEFAULTS={'game_path':'','baseline_path':'','source_lang':'en','api_base':'','model':'','timeout':120,'retries':10,'retry_policy_version':1,'batch_size':12,'concurrency':2,'batch_chars':6500,'max_tokens':8192,'interval':0.3,'json_mode':False,'monitor':False,'remember_key':False}

class Blob(ctypes.Structure):
    _fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_char))]

def crypt(raw, decrypt=False):
    if os.name!='nt': raise BridgeError('密钥加密保存仅支持 Windows；可取消记住密钥')
    lib=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[ctypes.c_void_p]; kernel.LocalFree.restype=ctypes.c_void_p
    buf=ctypes.create_string_buffer(raw)
    source=Blob(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_char))); output=Blob()
    fn=lib.CryptUnprotectData if decrypt else lib.CryptProtectData
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    fn.restype=wintypes.BOOL
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(output)):
        raise BridgeError('Windows 无法解密/加密此密钥。请重新填写；密钥未以明文保存。')
    try: return ctypes.string_at(output.pbData,output.cbData)
    finally: kernel.LocalFree(output.pbData)

def load(directory):
    path=pathlib.Path(directory)/'settings.json'; config=dict(DEFAULTS); key=''
    if path.exists():
        try:
            saved=json.loads(path.read_text(encoding='utf-8-sig'))
            config.update(saved)
            if 'retry_policy_version' not in saved:
                # Old versions stored a hidden default of 2. Adopt the user's
                # requested policy in memory; saving remains an explicit action.
                config['retries']=10
        except (ValueError,UnicodeError): raise BridgeError('设置文件损坏，请保留文件后检查 JSON 格式')
    else: config['game_path']=detect_game()
    blob=config.pop('api_key_protected','')
    if blob and config.get('remember_key'):
        key=crypt(base64.b64decode(blob),True).decode('utf-8')
    return config,key

def save(directory,config,key):
    safe={k:v for k,v in config.items() if k in DEFAULTS}
    if config.get('remember_key') and key:
        safe['api_key_protected']=base64.b64encode(crypt(key.encode('utf-8'))).decode('ascii')
    atomic_write(pathlib.Path(directory)/'settings.json',dumps(safe))
