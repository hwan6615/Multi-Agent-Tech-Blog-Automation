import os
import time
from typing import TypedDict, List
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from langchain_openai import ChatOpenAI, OpenAIEmbeddings  # [NEW] 임베딩 추가
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_community.tools.tavily_search import TavilySearchResults
from pymilvus import MilvusClient  # [NEW] Milvus 추가

import streamlit as st

# 1. 환경 설정
load_dotenv()

st.sidebar.write("### LangSmith 설정 확인")
st.sidebar.write(f"Tracing Enabled: {os.environ.get('LANGCHAIN_TRACING_V2')}")
st.sidebar.write(f"Project Name: {os.environ.get('LANGCHAIN_PROJECT')}")

# [NEW] Milvus & Embedding 설정
# [수정] Docker로 띄운 로컬 서버 연결
milvus_client = MilvusClient(uri="http://127.0.0.1:19530")
COLLECTION_NAME = "editor_feedback"

# 컬렉션이 없으면 생성 (Schema: id, vector, text, topic)
if not milvus_client.has_collection(COLLECTION_NAME):
    milvus_client.create_collection(
        collection_name=COLLECTION_NAME,
        dimension=1536,  # text-embedding-3-small 차원 수
        metric_type="COSINE",
        auto_id=True
    )

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tavily = TavilySearchResults(max_results=3)

# 2. State 정의 (에이전트끼리 주고받는 데이터)
class AgentState(TypedDict):
    topic: str              # 사용자가 입력한 주제
    research_data: str      # 검색된 정보
    draft: str              # 작성된 초안
    critique: str           # 편집자의 피드백
    revision_count: int     # 수정 횟수
    past_feedback: str      # [NEW] Milvus에서 검색한 과거의 피드백 기억

# 3. 노드(에이전트) 정의

def researcher_node(state: AgentState):
    """주제에 대해 검색을 수행합니다."""
    print("🔎 Researcher: 자료 조사 중...")
    query = state["topic"]
    search_results = tavily.invoke(query)
    data = "\n".join([r["content"] for r in search_results])
    return {"research_data": data}

def retrieve_memory(topic: str) -> str:
    """[NEW] Milvus에서 현재 주제와 관련된 과거 피드백을 검색합니다. (유사도 필터링 적용)"""
    try:
        # 1. 현재 주제를 벡터화
        vector = embeddings.embed_query(topic)
        
        # 2. Milvus에서 유사한 항목 검색
        results = milvus_client.search(
            collection_name=COLLECTION_NAME,
            data=[vector],
            limit=3,  # 가장 유사한 피드백 3개만 가져옴
            output_fields=["text", "topic"]
        )
        
        # 3. 결과가 아예 없는 경우 처리
        if not results or not results[0]:
            return "없음"

        # 4. [핵심 수정] 유사도 점수(distance)가 특정 기준(0.6) 이상인 것만 필터링
        valid_memories = []
        for res in results[0]:
            # distance(유사도)는 0~1 사이 값이며, 1에 가까울수록 유사함
            if res['distance'] >= 0.6:  
                formatted_memory = f"- {res['entity']['text']} (관련 주제: {res['entity']['topic']}, 유사도: {res['distance']:.2f})"
                valid_memories.append(formatted_memory)

        # 5. 필터링 후 남은 기억이 없는 경우
        if not valid_memories:
            return "없음 (관련된 과거 피드백이 충분히 유사하지 않음)"

        # 6. 유효한 기억만 반환
        return "\n".join(valid_memories)

    except Exception as e:
        print(f"Memory Retrieval Error: {e}")
        return "기억 장치 오류"

def writer_node(state: AgentState):
    """자료와 '과거의 기억'을 바탕으로 글을 씁니다."""
    print("✍️ Writer: 글 작성 중...")
    
    # [NEW] 글을 쓰기 전에 과거의 지적 사항(Long-term Memory)을 회상
    if state.get("past_feedback") is None:
        past_memory = retrieve_memory(state["topic"])
    else:
        past_memory = state["past_feedback"]

    # 초안 작성 모드
    if state.get("draft") is None:
        prompt = f"""
        당신은 테크 블로그 작가입니다. 다음 자료를 바탕으로 '{state['topic']}'에 대한 블로그 포스팅을 작성하세요.
        
        [⚠️ 중요: 과거의 실수 기억하기]
        이전에 에디터에게 지적받았던 다음 내용들을 주의하여 같은 실수를 반복하지 마세요:
        {past_memory}
        
        [조사 자료]
        {state['research_data']}
        
        서론-본론-결론 구조를 갖추고, 마크다운 형식으로 작성하세요.
        """
    # 수정 모드
    else:
        prompt = f"""
        당신은 글을 다듬는 에디터입니다. 아래의 [현재 초안]을 [편집자 피드백]을 반영하여 수정하세요.
        
        [현재 초안]
        {state['draft']}
        
        [편집자 피드백]
        {state['critique']}
        """

    messages = [HumanMessage(content=prompt)]
    response = llm.invoke(messages)
    
    # past_feedback도 state에 업데이트하여 계속 유지
    return {
        "draft": response.content, 
        "revision_count": state.get("revision_count", 0) + 1,
        "past_feedback": past_memory
    }

def editor_node(state: AgentState):
    """글을 검수하고, 유의미한 피드백은 Milvus에 저장합니다."""
    count = state.get("revision_count", 0)
    prev_critique = state.get("critique") # 직전 피드백 가져오기 (State에 저장된 값)
    
    print(f"🧐 Editor: 검수 중... (현재 {count}회차)")
    
    # 1. 3회 이상 수정했으면 강제 승인 (무한 루프 방지) - 이 부분은 유지!
    if count >= 3:
        prompt = f"""
        당신은 편집장입니다. 이미 3번이나 수정을 거쳤으므로, 
        치명적인 오류가 없다면 'ACCEPT'라고 답하여 승인하세요.
        [초안]
        {state['draft']}
        """
    # 2. 아직 기회가 남았으면 깐깐하게 검수 (여기를 수정!)
    else:
        # 이전 피드백이 있었다면, 그걸 잘 반영했는지 확인하는 지침 추가
        check_instruction = ""
        if prev_critique:
            check_instruction = f"""
            [⚠️ 강력한 검수 지침]
            직전에 당신은 작가에게 다음과 같은 피드백을 주었습니다:
            "{prev_critique}"
            
            작가가 위 피드백을 충실히 반영하여 글을 수정했는지 엄격하게 확인하세요.
            반영되지 않았다면 'REVISE'와 함께 "지난번 피드백(~~내용)이 반영되지 않았습니다"라고 구체적으로 지적하세요.
            """

        prompt = f"""
        당신은 깐깐한 편집장입니다. 
        {check_instruction}
        
        내용이 빈약하거나, 논리적 비약이 있거나, 문체가 어색하면 'REVISE'와 함께 구체적인 피드백을 주세요.
        완벽하다면 'ACCEPT'라고만 답하세요.
        [초안]
        {state['draft']}
        """
        
    messages = [HumanMessage(content=prompt)]
    response = llm.invoke(messages)
    critique_text = response.content

    # 반려(REVISE)일 경우, 해당 피드백을 Milvus에 영구 저장 (학습)
    if "REVISE" in critique_text:
        try:
            # 피드백 내용만 추출 (REVISE 단어 제거 등 전처리는 간소화함)
            vector = embeddings.embed_query(state["topic"])
            milvus_client.insert(
                collection_name=COLLECTION_NAME,
                data=[{
                    "vector": vector,
                    "text": critique_text,
                    "topic": state["topic"],
                    # "timestamp": time.time() # 필요시 import time 하고 주석 해제
                }]
            )
            print("💾 Editor: 피드백을 장기 기억(Milvus)에 저장했습니다.")
        except Exception as e:
            print(f"Milvus Insert Error: {e}")

    return {"critique": critique_text}

# 4. 엣지(흐름 제어) 정의
def router(state: AgentState):
    critique = state["critique"]
    count = state["revision_count"]
    if "ACCEPT" in critique or count >= 3:
        return "end"
    else:
        return "revise"

# 5. 그래프(Workflow) 조립
workflow = StateGraph(AgentState)

workflow.add_node("researcher", researcher_node)
workflow.add_node("writer", writer_node)
workflow.add_node("editor", editor_node)

workflow.set_entry_point("researcher")
workflow.add_edge("researcher", "writer")
workflow.add_edge("writer", "editor")

workflow.add_conditional_edges(
    "editor",
    router,
    {"revise": "writer", "end": END}
)

app = workflow.compile()

# 실행 및 테스트 (Streamlit 연동)
st.title("🧠 Memory-Augmented AI Team (with Milvus)")
st.caption("Researcher ➡️ Writer (Recalls Memory) 🔄 Editor (Saves Feedback)")

topic = st.text_input("주제를 입력하세요", "LangGraph와 LangChain의 차이점")

if st.button("팀 실행하기"):
    with st.status("AI 팀이 협업 중입니다...", expanded=True) as status:
        initial_state = {
            "topic": topic,
            "revision_count": 0,
            "critique": None,
            "past_feedback": None
        }
        
        latest_draft = ""
        
        for output in app.stream(initial_state):
            for key, value in output.items():
                if "draft" in value:
                    latest_draft = value["draft"]

                if key == "researcher":
                    st.write("🔎 **Researcher**: 자료 조사 완료")
                    
                elif key == "writer":
                    count = value.get("revision_count", 0)
                    memory = value.get("past_feedback", "없음")
                    
                    st.write(f"✍️ **Writer**: 초안 작성 완료 (Rev {count})")
                    if count == 1: # 첫 작성 시에만 기억 표시
                        with st.expander("🧠 활성화된 장기 기억 (Milvus)"):
                            st.info(memory)
                    
                elif key == "editor":
                    critique = value.get("critique", "")
                    if "ACCEPT" in critique:
                        st.write("✅ **Editor**: 승인! (완벽합니다)")
                    else:
                        st.write("❌ **Editor**: 반려! (피드백을 학습합니다)")
                        st.warning(f"피드백: {critique}")
                        
        status.update(label="작업 완료!", state="complete")

    if latest_draft:
        st.divider()
        st.subheader("📄 최종 블로그 포스팅")
        st.markdown(latest_draft)
    else:
        st.error("초안이 생성되지 않았습니다.")