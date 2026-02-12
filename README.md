# 🤖 AI Editor Team: Multi-Agent Tech Blog Automation

이 프로젝트는 LangGraph를 활용하여 여러 AI 에이전트가 협업하고 서로의 결과물을 검수하며 고품질의 테크 블로그 포스팅을 자동 생성하는 자율형 멀티 에이전트 시스템입니다.

---

## 🌟 Linear Chain vs. Agentic Workflow

| 구분 | Linear Chain (기존 방식) | **Agentic Workflow (현재 프로젝트)** |
| :--- | :--- | :--- |
| **흐름 제어** | 순차적 실행 (A → B → C) | 상태 기반 순환 (Cyclic Loop) |
| **품질 관리** | 한 번 생성 후 종료 | 에디터의 피드백 및 재작성 루프 |
| **자율성** | 정해진 순서만 따름 | 조건부 분기(Router)를 통한 자율 결정 |
| **유연성** | 중간 오류 대응 어려움 | Self-Correction (자가 수정) 가능 |

---

## 🏗️ 시스템 아키텍처

본 시스템은 StateGraph를 중심으로 세 가지 전문 에이전트가 데이터(State)를 공유하며 협업합니다.

1. **Researcher Agent**: Tavily Search API를 사용하여 주제와 관련된 최신 웹 정보를 수집합니다.
2. **Writer Agent**: 수집된 자료와 에디터의 피드백을 반영하여 블로그 초안을 작성하거나 수정합니다.
3. **Editor Agent**: 작성된 초안을 검수하고 승인(ACCEPT) 또는 반려(REVISE) 피드백을 제공합니다.
4. **Conditional Router**: 편집자의 평가에 따라 프로세스를 종료할지 또는 작가에게 재작성을 요청할지 결정합니다.

---

## 🖼️ Dashboard Demo

![Dashboard Demo](demo_img.png)
*RAG 기반 에이전트가 전체 도구 라이브러리에서 의미론적 유사도를 기반으로 도구를 추출하고 추론하는 과정입니다.*

---

## 🚀 주요 기능
* **Cyclic Feedback Loop**: 에디터 에이전트가 만족할 때까지 최대 3회까지 글을 다듬는 자가 수정 메커니즘을 갖추고 있습니다.
* **State Management**: LangGraph의 AgentState를 통해 에이전트 간 대화 맥락과 작업 이력을 완벽하게 공유합니다.
* **Real-time Web Research**: 최신 테크 트렌드를 반영하기 위해 실시간 웹 검색 도구를 통합했습니다.
* **Interactive Dashboard**: Streamlit을 통해 에이전트 간의 협업 과정과 피드백 내용을 실시간으로 시각화합니다.

---

## 🛠️ 기술 스택
* **Orchestration**: LangGraph, LangChain
* **LLM API**: OpenAI (gpt-4o-mini)
* **Search Engine**: Tavily API
* **Interface**: Streamlit
* **Environment**: Python 3.12, uv, python-dotenv

---

## 📦 설치 및 실행 방법
### 1. 환경 설정 및 의존성 설치
 - uv를 사용하여 가상환경을 구축하고 필요한 패키지를 설치합니다.
```bash
# uv 설치 (이미 설치된 경우 생략)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 의존성 설치 및 가상환경 동기화
uv sync
```

### 2. 환경 변수 설정
 - 프로젝트 최상단에 .env 파일을 생성하고 API 키를 입력합니다.
```bash
OPENAI_API_KEY=your_openai_api_key
TAVILY_API_KEY=your_tavily_api_key
```

### 3. 실행
```bash
# Streamlit 데모 실행
uv run streamlit run app.py
```

---

## 📈 프로젝트 성과 및 인사이트
 - 에이전트 협업 효율화: 단일 LLM 호출보다 다각도 검수를 통해 정보의 정확도와 문장 구조의 완성도가 획기적으로 향상되었습니다.
 - 제어 가능한 자율성: 무한 루프 방지 로직과 단계별 프롬프트 최적화를 통해 실무에서 사용 가능한 수준의 에이전트 워크플로우를 구현했습니다.
 - 최신 정보의 결합: 정적 학습 데이터의 한계를 웹 검색 도구와의 유기적인 결합으로 극복했습니다.
