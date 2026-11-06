"""Windows Core Audio control. COM pointers stay on the calling thread."""
import ctypes as C
from ctypes import wintypes as W
from contextlib import contextmanager
import os
import uuid

class GUID(C.Structure):
    _fields_=[('data',C.c_ubyte*16)]
    def __init__(self,value):
        super().__init__(); C.memmove(C.byref(self),uuid.UUID(value).bytes_le,16)

ENUMERATOR=GUID('BCDE0395-E52F-467C-8E3D-C4579291692E')
ENUMERATOR_IID=GUID('A95664D2-9614-4F35-A746-DE8DB63617E6')
ENDPOINT_IID=GUID('5CDF2C82-841E-4546-9722-0CF74078229A')
SESSION_MANAGER_IID=GUID('77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F')
SESSION_CONTROL2_IID=GUID('BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D')
SIMPLE_VOLUME_IID=GUID('87CE5498-68D6-44E5-9215-6DA47EF883D8')

def call(ptr,index,args,*values):
    table=C.cast(ptr,C.POINTER(C.POINTER(C.c_void_p))).contents
    func=C.WINFUNCTYPE(C.c_long,C.c_void_p,*args)(table[index])
    result=func(ptr,*values)
    if result<0: raise OSError('Core Audio HRESULT 0x%08X'%(result&0xffffffff))
    return result

def release(ptr):
    if ptr: call(ptr,2,[])

@contextmanager
def query(ptr,iid):
    out=C.c_void_p()
    call(ptr,0,[C.POINTER(GUID),C.POINTER(C.c_void_p)],C.byref(iid),C.byref(out))
    try: yield out
    finally: release(out)

class WindowsAudio:
    """Boost only current playback endpoints and this application's own mixer session."""
    def __init__(self):
        self.ole=C.OleDLL('ole32')
        self.ole.CoInitializeEx.argtypes=[C.c_void_p,W.DWORD]
        self.ole.CoInitializeEx.restype=C.c_long
        result=self.ole.CoInitializeEx(None,0)
        if result<0: raise OSError('Audio COM initialization failed')
        self.enumerator=C.c_void_p();self.endpoints={};self.sessions={};self.closed=False
        self.ole.CoCreateInstance.argtypes=[C.POINTER(GUID),C.c_void_p,W.DWORD,C.POINTER(GUID),C.POINTER(C.c_void_p)]
        self.ole.CoCreateInstance.restype=C.c_long
        result=self.ole.CoCreateInstance(C.byref(ENUMERATOR),None,23,C.byref(ENUMERATOR_IID),C.byref(self.enumerator))
        if result<0:
            self.ole.CoUninitialize();raise OSError('Audio device enumeration unavailable')

    @contextmanager
    def device(self,role=None,device_id=None):
        ptr=C.c_void_p()
        if device_id is not None:
            call(self.enumerator,5,[W.LPCWSTR,C.POINTER(C.c_void_p)],device_id,C.byref(ptr))
        else:
            call(self.enumerator,4,[C.c_int,C.c_int,C.POINTER(C.c_void_p)],0,role,C.byref(ptr))
        try:yield ptr
        finally:release(ptr)

    def device_id(self,device):
        value=C.c_void_p()
        call(device,5,[C.POINTER(C.c_void_p)],C.byref(value))
        try:return C.wstring_at(value)
        finally:
            self.ole.CoTaskMemFree.argtypes=[C.c_void_p];self.ole.CoTaskMemFree(value)

    @contextmanager
    def activate(self,device,iid):
        out=C.c_void_p()
        call(device,3,[C.POINTER(GUID),W.DWORD,C.c_void_p,C.POINTER(C.c_void_p)],C.byref(iid),23,None,C.byref(out))
        try:yield out
        finally:release(out)

    @staticmethod
    def read_endpoint(volume):
        level=C.c_float();mute=W.BOOL()
        call(volume,9,[C.POINTER(C.c_float)],C.byref(level))
        call(volume,15,[C.POINTER(W.BOOL)],C.byref(mute))
        return {'volume':round(level.value,6),'muted':bool(mute.value)}

    @staticmethod
    def set_endpoint(volume,level,mute):
        call(volume,7,[C.c_float,C.c_void_p],float(level),None)
        call(volume,14,[W.BOOL,C.c_void_p],bool(mute),None)

    @contextmanager
    def own_sessions(self,device):
        pointers=[]
        try:
            with self.activate(device,SESSION_MANAGER_IID) as manager:
                enum=C.c_void_p()
                call(manager,5,[C.POINTER(C.c_void_p)],C.byref(enum))
                try:
                    count=C.c_int();call(enum,3,[C.POINTER(C.c_int)],C.byref(count))
                    for index in range(count.value):
                        control=C.c_void_p();call(enum,4,[C.c_int,C.POINTER(C.c_void_p)],index,C.byref(control))
                        try:
                            with query(control,SESSION_CONTROL2_IID) as control2:
                                pid=W.DWORD();call(control2,14,[C.POINTER(W.DWORD)],C.byref(pid))
                                if pid.value!=os.getpid():continue
                                identity=C.c_void_p();call(control2,13,[C.POINTER(C.c_void_p)],C.byref(identity))
                                try:key=C.wstring_at(identity)
                                finally:self.ole.CoTaskMemFree(identity)
                            volume=C.c_void_p();call(control,0,[C.POINTER(GUID),C.POINTER(C.c_void_p)],C.byref(SIMPLE_VOLUME_IID),C.byref(volume))
                            pointers.append((key,volume))
                        finally:release(control)
                finally:release(enum)
            yield pointers
        finally:
            for _,ptr in pointers:release(ptr)

    def snapshot(self):
        values=[];seen=set()
        for role in (0,1):
            with self.device(role=role) as device:
                key=self.device_id(device)
                if key in seen:continue
                seen.add(key)
                with self.activate(device,ENDPOINT_IID) as volume:values.append(self.read_endpoint(volume))
        return values

    def ensure_loud(self,minimum=0.8):
        seen=set();success=0;errors=[]
        for role in (0,1):
            try:
                with self.device(role=role) as device:
                    key=self.device_id(device)
                    if key in seen:continue
                    seen.add(key)
                    with self.activate(device,ENDPOINT_IID) as volume:
                        state=self.read_endpoint(volume)
                        if key not in self.endpoints:self.endpoints[key]=state
                        self.set_endpoint(volume,max(minimum,state['volume']),False)
                    # PlaySound may create its session just after playback starts; repeat each tick.
                    with self.own_sessions(device) as sessions:
                        for identity,volume in sessions:
                            level=C.c_float();mute=W.BOOL()
                            call(volume,4,[C.POINTER(C.c_float)],C.byref(level));call(volume,6,[C.POINTER(W.BOOL)],C.byref(mute))
                            self.sessions.setdefault((key,identity),(level.value,bool(mute.value)))
                            call(volume,3,[C.c_float,C.c_void_p],1.0,None);call(volume,5,[W.BOOL,C.c_void_p],False,None)
                    success+=1
            except OSError as error:errors.append(str(error))
        if not success:raise OSError('; '.join(errors) or 'No playback device')

    def close(self):
        if self.closed:return
        self.closed=True
        errors=[]
        for key,state in self.endpoints.items():
            try:
                with self.device(device_id=key) as device:
                    try:
                        with self.own_sessions(device) as sessions:
                            for identity,volume in sessions:
                                original=self.sessions.get((key,identity))
                                if original is not None:
                                    call(volume,3,[C.c_float,C.c_void_p],original[0],None);call(volume,5,[W.BOOL,C.c_void_p],original[1],None)
                    finally:
                        with self.activate(device,ENDPOINT_IID) as volume:self.set_endpoint(volume,state['volume'],state['muted'])
            except OSError as error:errors.append(str(error))
        release(self.enumerator);self.ole.CoUninitialize()
        if errors:raise OSError('Previous audio setting restore failed: '+'; '.join(errors))

if __name__=='__main__':
    import json
    audio=WindowsAudio()
    try:print(json.dumps(audio.snapshot()))
    finally:audio.close()
