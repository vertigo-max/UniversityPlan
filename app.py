import json
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒")

# session_state 의 예약어(.items())와 겹치지 않도록 키 이름을 따로 둔다
LIST_KEY = "shopping_list"
DATA_FILE = Path(__file__).parent / "shopping_list.json"


# ---------- 파일 저장 / 불러오기 ----------
def load_data():
    """저장 파일을 읽어 (아이템 목록, 다음 id)를 돌려준다. 없거나 깨졌으면 빈 목록."""
    if not DATA_FILE.exists():
        return [], 1
    try:
        with DATA_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
        items = [
            {
                "id": int(i["id"]),
                "name": str(i["name"]),
                "qty": int(i.get("qty", 1)),
                "done": bool(i.get("done", False)),
            }
            for i in data.get("items", [])
        ]
        next_id = int(data.get("next_id", 1))
        # 파일이 어긋나 있어도 id 가 겹치지 않도록 보정
        next_id = max([next_id] + [i["id"] + 1 for i in items])
        return items, next_id
    except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
        st.warning(f"저장 파일을 읽지 못해 빈 목록으로 시작합니다: {DATA_FILE.name}")
        return [], 1


def save_data():
    """현재 목록을 파일에 기록한다."""
    payload = {
        "next_id": st.session_state.next_id,
        "items": st.session_state[LIST_KEY],
    }
    try:
        with DATA_FILE.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError as e:
        st.error(f"저장에 실패했습니다: {e}")


# ---------- 상태 초기화 ----------
def init_state():
    if LIST_KEY not in st.session_state:
        # 각 아이템: {"id": int, "name": str, "qty": int, "done": bool}
        items, next_id = load_data()
        st.session_state[LIST_KEY] = items
        st.session_state.next_id = next_id
    if "editing_id" not in st.session_state:
        st.session_state.editing_id = None


def add_item(name: str, qty: int):
    name = name.strip()
    if not name:
        st.warning("아이템 이름을 입력해 주세요.")
        return
    st.session_state[LIST_KEY].append(
        {"id": st.session_state.next_id, "name": name, "qty": qty, "done": False}
    )
    st.session_state.next_id += 1
    save_data()


def delete_item(item_id: int):
    st.session_state[LIST_KEY] = [
        i for i in st.session_state[LIST_KEY] if i["id"] != item_id
    ]
    if st.session_state.editing_id == item_id:
        st.session_state.editing_id = None
    save_data()


init_state()

st.title("🛒 쇼핑 리스트")

# ---------- 아이템 추가 ----------
with st.form("add_form", clear_on_submit=True):
    col_name, col_qty, col_btn = st.columns([3, 1, 1])
    new_name = col_name.text_input(
        "아이템", placeholder="예) 우유", label_visibility="collapsed"
    )
    new_qty = col_qty.number_input(
        "수량", min_value=1, step=1, value=1, label_visibility="collapsed"
    )
    submitted = col_btn.form_submit_button("추가", use_container_width=True)

if submitted:
    add_item(new_name, int(new_qty))

st.divider()

# ---------- 목록 ----------
items = st.session_state[LIST_KEY]

if not items:
    st.info("아직 담은 아이템이 없습니다. 위에서 추가해 보세요.")
else:
    for item in items:
        item_id = item["id"]

        # 수정 모드
        if st.session_state.editing_id == item_id:
            c1, c2, c3, c4 = st.columns([4, 1.2, 1, 1])
            edited_name = c1.text_input(
                "이름",
                value=item["name"],
                key=f"edit_name_{item_id}",
                label_visibility="collapsed",
            )
            edited_qty = c2.number_input(
                "수량",
                min_value=1,
                step=1,
                value=item["qty"],
                key=f"edit_qty_{item_id}",
                label_visibility="collapsed",
            )
            if c3.button("저장", key=f"save_{item_id}", use_container_width=True):
                if edited_name.strip():
                    item["name"] = edited_name.strip()
                    item["qty"] = int(edited_qty)
                    st.session_state.editing_id = None
                    save_data()
                    st.rerun()
                else:
                    st.warning("아이템 이름은 비울 수 없습니다.")
            if c4.button("취소", key=f"cancel_{item_id}", use_container_width=True):
                st.session_state.editing_id = None
                st.rerun()

        # 일반 모드
        else:
            c1, c2, c3 = st.columns([6, 1, 1])

            label = f"~~{item['name']}  ×{item['qty']}~~" if item["done"] else f"{item['name']}  ×{item['qty']}"
            checked = c1.checkbox(label, value=item["done"], key=f"check_{item_id}")
            if checked != item["done"]:
                item["done"] = checked
                save_data()
                st.rerun()

            if c2.button("수정", key=f"edit_{item_id}", use_container_width=True):
                st.session_state.editing_id = item_id
                st.rerun()

            if c3.button("삭제", key=f"del_{item_id}", use_container_width=True):
                delete_item(item_id)
                st.rerun()

    st.divider()

    done_count = sum(1 for i in items if i["done"])
    st.caption(
        f"전체 {len(items)}개 · 완료 {done_count}개 · 남음 {len(items) - done_count}개"
    )

    b1, b2 = st.columns(2)
    if b1.button("완료 항목 삭제", use_container_width=True):
        st.session_state[LIST_KEY] = [i for i in items if not i["done"]]
        st.session_state.editing_id = None
        save_data()
        st.rerun()
    if b2.button("전체 삭제", use_container_width=True):
        st.session_state[LIST_KEY] = []
        st.session_state.editing_id = None
        save_data()
        st.rerun()
