# 라그나로크 빛과 어둠의 황녀 (PSP) 비공식 한글패치

PSP 일본판 **ラグナロク～光と闇の皇女～ (NPJH-50431)** 비공식 한국어 패치입니다. 이 저장소에는 제작 도구와 기술 문서만 있고, 패치 파일(xdelta)은 [Releases](../../releases)에서 받을 수 있습니다. 게임 원본·일본어 원문·번역 대본은 포함하지 않습니다.

## 적용 방법
1. 아래 해시와 일치하는 **원본 `.iso`** 를 준비합니다. (CSO·CHD 등으로 변환한 이미지에는 적용할 수 없습니다.)
   - PowerShell: `Get-FileHash -Algorithm MD5 -LiteralPath '.\Ragnarok - Hikari to Yami no Koujo (Japan).iso'`
2. xdeltaUI 같은 도구로 원본에 `Ragnarok_Hikari_to_Yami_no_Koujo_KO_v1.0.2.xdelta` 를 적용합니다.
   - 명령줄: `xdelta3 -d -s "Ragnarok - Hikari to Yami no Koujo (Japan).iso" Ragnarok_Hikari_to_Yami_no_Koujo_KO_v1.0.2.xdelta "Ragnarok - Hikari to Yami no Koujo (Korean).iso"`
3. 만들어진 ISO를 PPSSPP 또는 커스텀 펌웨어에서 실행합니다.

| 항목 | 값 |
| --- | --- |
| 원본 ISO 크기 | 667,385,856 바이트 |
| 원본 ISO MD5 | `fa0f7c65c5190f5ed2dad6594a3bd974` |
| 원본 ISO SHA-256 | `745b8bf2e2ff542b9c64b6fe21e0130f086cadbfd662c6084e78a1dc81afdbca` |
| xdelta SHA-256 | `4f4574c9f3d949557dc01e7bad2347a86cce93f63f054856f24dd6523e36deea` |
| 결과 ISO 크기 | 668,035,072 바이트 |
| 결과 ISO SHA-256 | `276adb9312050bd164949e8a27c548625cbc1ec387780af05d120d6d6af3116d` |

## 주의
- EBOOT를 복호화한 평문 ELF로 넣었기 때문에 **PPSSPP·커스텀 펌웨어 전용**입니다. 정품 펌웨어에서는 부팅되지 않습니다.
- **타이틀 메뉴의 INSTALL(설치) 기능은 쓰지 마세요.** 설치 데이터는 원본(일본어, 암호화)이라 고칠 수 없어서, 패치는 설치 데이터를 무시하고 항상 디스크에서 읽습니다.

## 한글화 내용
- 이벤트·전투·마을·사이드 스토리 대사: 스크립트 499개 파일, 고유 문장 7,978개
- 실행 파일 문자열 2,750개: 아이템·장비·스킬·몬스터·인물 이름, 효과 설명, 퀘스트 제목·요약, 시스템 메시지
- 세이브·설치·메모리스틱 관련 시스템 메시지(UTF-8) 24개, XMB 게임 제목
- 그림 글자 약 340장: 타이틀 로고의 일본어 부분, 캐릭터 메이킹, 옵션, 스테이터스, 상점, 월드맵, 전투 준비·전투 UI, 이벤트 제목, 지역명, 승패 조건, 달력, 도움말(튜토리얼) 전 페이지
- 직업·스킬·몬스터·아이템 이름은 한국 라그나로크 온라인 공식 표기를 따랐습니다.
- 글꼴: 게임 자체 PGF 폰트에 나눔스퀘어네오로 한글 1,164자 추가 (본문 Bold 15px, 보조 Regular 12px)

## 그대로 둔 것
- 이름 입력 자판(가나)과 이름 입력 금지어 목록 — 기본 이름은 「리토」로 표시됩니다. 대사 속 이름 뒤 조사는 「을(를)」처럼 표기한 곳이 있습니다.
- 동영상(오프닝 내레이션 자막 포함), 엔딩 스태프롤 영상, 제작사 로고, 영문 장식 문구, 카드 일러스트
- 도움말 화면 캡처 속 판독하기 어려운 아주 작은 글자

## 검증 범위
PPSSPP에서 오프닝, 타이틀, 캐릭터 메이킹, 도움말, 첫 이벤트, 월드맵, 전투 준비, 첫 전투까지 확인했습니다. 전체 플레이 검증은 하지 않았습니다.

## 문서
- [CHANGELOG.md](CHANGELOG.md) — 변경 기록
- [docs/TECHNICAL.md](docs/TECHNICAL.md) — 파일 형식과 한글화 방법
- [docs/BUILD.md](docs/BUILD.md) — 직접 빌드하는 방법
- [docs/FONT_CREDITS.md](docs/FONT_CREDITS.md) — 글꼴
- [RIGHTS.md](RIGHTS.md) — 권리 및 외부 자료
