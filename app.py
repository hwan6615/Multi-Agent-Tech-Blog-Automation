import os
from typing import TypedDict, List
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_community.tools.tavily_search import TavilySearchResults

import streamlit as st
    
# 1. 환경 설정
load_dotenv()

st.sidebar.write("### LangSmith 설정 확인")
st.sidebar.write(f"Tracing Enabled: {os.environ.get('LANGCHAIN_TRACING_V2')}")
st.sidebar.write(f"Project Name: {os.environ.get('LANGCHAIN_PROJECT')}")
api_key = os.environ.get('LANGCHAIN_API_KEY')
if api_key:
    st.sidebar.write(f"API Key Loaded: {api_key[:5]}...") # 키 앞부분만 확인
else:
    st.sidebar.error("API Key가 없습니다! .env를 확인하세요.")
    
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tavily = TavilySearchResults(max_results=3)

# 2. State 정의 (에이전트끼리 주고받는 데이터)
class AgentState(TypedDict):
    topic: str              # 사용자가 입력한 주제
    research_data: str      # 검색된 정보
    draft: str              # 작성된 초안
    critique: str           # 편집자의 피드백
    revision_count: int     # 수정 횟수 (무한 루프 방지)

# 3. 노드(에이전트) 정의

def researcher_node(state: AgentState):
    """주제에 대해 검색을 수행합니다."""
    print("🔎 Researcher: 자료 조사 중...")
    query = state["topic"]
    search_results = tavily.invoke(query)
    # 검색 결과를 문자열로 합침
    data = "\n".join([r["content"] for r in search_results])
    return {"research_data": data}

def writer_node(state: AgentState):
    """자료를 바탕으로 글을 씁니다."""
    print("✍️ Writer: 글 작성 중...")
    
    # 초안이 없으면 새로 쓰고, 있으면 수정 모드로 진입
    if state.get("draft") is None:
        prompt = f"""
        당신은 테크 블로그 작가입니다. 다음 자료를 바탕으로 '{state['topic']}'에 대한 블로그 포스팅을 작성하세요.
        서론-본론-결론 구조를 갖추고, 마크다운 형식으로 작성하세요.
        
        [조사 자료]
        {state['research_data']}
        """
    else:
        prompt = f"""
        당신은 글을 다듬는 에디터입니다. 아래의 [현재 초안]을 [편집자 피드백]을 반영하여 수정하세요.
        전체를 새로 쓰지 말고, 지적된 부분 위주로 개선하여 완성도를 높이세요.
        
        [현재 초안]
        {state['draft']}
        
        [편집자 피드백]
        {state['critique']}
        """

    messages = [HumanMessage(content=prompt)]
    response = llm.invoke(messages)
    return {"draft": response.content, "revision_count": state.get("revision_count", 0) + 1}

def editor_node(state: AgentState):
    """글을 검수합니다."""
    count = state.get("revision_count", 0)
    print(f"🧐 Editor: 검수 중... (현재 {count}회차)")
    
    # 3번째 수정이면 웬만하면 승인하도록 유도
    if count >= 3:
        prompt = f"""
        당신은 편집장입니다. 아래 초안을 검토하세요.
        이미 3번이나 수정을 거쳤으므로, 치명적인 오류가 없다면 'ACCEPT'라고 답하여 승인하세요.
        
        [초안]
        {state['draft']}
        """
    else:
        prompt = f"""
        당신은 깐깐한 편집장입니다. 아래 초안을 검토하세요.
        내용이 빈약하거나, 논리적 비약이 있거나, 문체가 어색하면 'REVISE'와 함께 구체적인 피드백을 주세요.
        완벽하다면 'ACCEPT'라고만 답하세요.
        
        [초안]
        {state['draft']}
        """
        
    messages = [HumanMessage(content=prompt)]
    response = llm.invoke(messages)
    return {"critique": response.content}

# 4. 엣지(흐름 제어) 정의
def router(state: AgentState):
    """편집자의 평가에 따라 다음 단계를 결정"""
    critique = state["critique"]
    count = state["revision_count"]
    
    # 3번 이상 수정했거나, 편집자가 승인하면 종료
    if "ACCEPT" in critique or count >= 3:
        return "end"
    else:
        return "revise" # 다시 Writer에게

# 5. 그래프(Workflow) 조립
workflow = StateGraph(AgentState)

# 노드 추가
workflow.add_node("researcher", researcher_node)
workflow.add_node("writer", writer_node)
workflow.add_node("editor", editor_node)

# 흐름 연결
workflow.set_entry_point("researcher")
workflow.add_edge("researcher", "writer")
workflow.add_edge("writer", "editor")

# 조건부 분기 (핵심!)
workflow.add_conditional_edges(
    "editor",
    router,
    {
        "revise": "writer", # 반려되면 다시 씀
        "end": END          # 통과되면 끝
    }
)

# 컴파일
app = workflow.compile()


# 실행 및 테스트 (Streamlit 연동)
st.title("🤖 AI Tech Blog Team (LangGraph)")
st.caption("Researcher ➡️ Writer 🔄 Editor (Cyclic Workflow)")

topic = st.text_input("주제를 입력하세요 (예: LLM 에이전트의 미래)", "LangGraph의 장점")

if st.button("팀 실행하기"):
    with st.status("AI 팀이 협업 중입니다...", expanded=True) as status:
        initial_state = {
            "topic": topic,
            "revision_count": 0,
            "critique": None
        }
        
        latest_draft = ""  # 👈 [핵심] 초안을 저장할 변수 초기화
        
        # 그래프 실행 및 과정 시각화
        for output in app.stream(initial_state):
            for key, value in output.items():
                
                # ✍️ Writer가 실행될 때마다 초안을 따로 저장해둡니다!
                if "draft" in value:
                    latest_draft = value["draft"]

                if key == "researcher":
                    st.write("🔎 **Researcher**: 자료 조사 완료")
                    with st.expander("수집된 데이터 확인"):
                        # research_data가 없을 경우 방어 코드 추가
                        data = value.get("research_data", "데이터 없음")
                        st.write(data[:500] + "...")
                        
                elif key == "writer":
                    count = value.get("revision_count", 0)
                    st.write(f"✍️ **Writer**: 초안 작성 완료 (Rev {count})")
                    
                elif key == "editor":
                    critique = value.get("critique", "")
                    if "ACCEPT" in critique:
                        st.write("✅ **Editor**: 승인! (완벽합니다)")
                    else:
                        st.write("❌ **Editor**: 반려! (다시 쓰세요)")
                        st.warning(f"피드백: {critique}")
                        
        status.update(label="작업 완료!", state="complete")

    # 📄 저장해둔 최신 초안을 마지막에 출력
    if latest_draft:
        st.divider()
        st.subheader("📄 최종 블로그 포스팅")
        st.markdown(latest_draft)
    else:
        st.error("초안이 생성되지 않았습니다.")