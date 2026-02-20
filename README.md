# 📍 Excel Map Editor (엑셀 지도 편집기)

엑셀 파일에 저장된 주소들을 한눈에 지도에 표시하고, 예쁜 이미지로 저장할 수 있는 파이썬 프로그램입니다. 최근 리팩토링을 통해 코드 품질을 높이고 유지보수가 용이한 모듈형 구조로 개편되었습니다.

## ✨ 주요 개선 사항
- **코드 모듈화**: 단일 파일에서 기능별 모듈 구조로 개편되어 확장성이 뛰어납니다.
- **한국어 로컬라이징**: 모든 코드 주석, 독스트링 및 UI 메시지가 한국어로 현지화되었습니다.
- **최첨단 렌더링**: 라벨 겹침 방지 알고리즘(Force-Directed Repulsion)이 적용된 하이브리드 지도 엔진을 탑재했습니다.

## 🚀 주요 기능
- **엑셀 업로드**: 주소가 적힌 엑셀 파일을 올리면 자동으로 지도에 핀을 찍어줍니다.
- **똑똑한 주소 검색**: 주소가 조금 틀려도 알아서 최적의 위치를 찾아냅니다 (Vworld API 활용).
- **이미지 저장**: 만들어진 지도를 PNG 이미지로 깔끔하게 저장할 수 있습니다.
- **내 맘대로 꾸미기**: 핀의 색상, 크기, 라벨 방향을 자유롭게 조절하세요.

## 📁 프로젝트 구조
- `map_app.py`: 메인 애플리케이션 핸들러 및 GUI (Tkinter)
- `config.py`: API 엔드포인트 및 UI 설정값 중앙 관리
- `utils/geocoding.py`: Vworld API 연동 및 주소 정규화 엔진
- `utils/geo_utils.py`: 지리 좌표 투영 및 뷰포트 계산 유틸리티
- `renderer/map_renderer.py`: 지도 마커 및 지능형 라벨 배치 엔진

## 🛠 실행 방법
1. **파이썬 설치**: Python 3.8+ 버전이 필요합니다.
2. **라이브러리 설치**:
   ```bash
   pip install ttkbootstrap pandas requests pillow openpyxl
   ```
3. **프로그램 실행**:
   ```bash
   python map_app.py
   ```

## 📦 실행 파일(EXE) 만들기
PyInstaller를 사용하여 멀티 모듈 구조를 단일 파일로 빌드할 수 있습니다.
```bash
pyinstaller --noconsole --onefile --name "ExcelMapEditor" --hidden-import "config" map_app.py
```

## ⚠️ 참고 사항
- **API 키**: 지도를 불러와 주소를 검색하려면 [Vworld](https://www.vworld.kr)에서 발급받은 API 키가 필요합니다.
- **보안**: API 키는 로컬 `config.json`에 안전하게 저장되며, Git 기록에 포함되지 않습니다.
