"""Generate disposable test data, never a real pairing secret."""
import json
from pathlib import Path
import companion
root=Path(__file__).resolve().parent
pair=companion.new_pairing('Integration test laptop')
msg=companion.message('test','암호화 통합 테스트입니다. 실제 사용자 정보는 포함하지 않습니다.')
vector={'pair':pair,'code':companion.pairing_code(pair),'message':msg,'envelope':companion.seal(pair,msg).decode()}
path=root/'android/app/src/androidTest/assets/vector.json'
path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(vector,ensure_ascii=False),encoding='utf-8')
print('Disposable test vector generated. Do not use it for a real phone.')
