import json
import os
from datetime import datetime
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒")

DATA_FILE = Path(__file__).parent / "shopping_list.json"


# ---------- 파일 저장 / 불러오기 ----------
# 목록의 원본은 항상 "파일"이다. 화면을 그릴 때마다 파일에서 읽어오므로
# 새로고침하든, 탭을 여러 개 띄우든, 서버를 재시작하든 같은 내용을 보게 된다.
def load_data():
    """저장 파일에서 (아이템 목록, 다음 id)를 읽는다."""
    if not DATA_FILE.exists() or DATA_FILE.stat().st_size == 0:
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
            for i in data["items"]
        ]
    except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError) as e:
        # 깨진 파일을 조용히 빈 목록으로 덮어쓰면 데이터가 영영 사라진다.
        # 원본을 따로 보관해 두고, 사용자에게 분명히 알린다.
        backup = DATA_FILE.with_name(
            f"{DATA_FILE.stem}.손상됨-{datetime.now():%Y%m%d-%H%M%S}.json"
        )
        try:
            DATA_FILE.rename(backup)
            st.error(
                f"저장 파일을 읽지 못했습니다 ({e}). "
                f"원본은 `{backup.name}` 으로 백업해 두었고 빈 목록으로 시작합니다."
            )
        except OSError:
            st.error(f"저장 파일을 읽지 못했습니다: {e}")
        return [], 1

    next_id = max([int(data.get("next_id", 1))] + [i["id"] + 1 for i in items])
    return items, next_id


def save_data(items, next_id):
    """임시 파일에 먼저 쓰고 통째로 바꿔치기한다(원자적 저장).

    바로 덮어쓰면 저장 도중 프로세스가 죽거나 동기화 프로그램이 끼어들 때
    내용이 잘린 파일이 남고, 그 다음 실행에서 목록이 통째로 사라진다.
    """
    tmp = DATA_FILE.with_name(DATA_FILE.name + ".tmp")
    payload = {"next_id": next_id, "items": items}
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, DATA_FILE)
    except OSError as e:
        st.error(f"저장에 실패했습니다: {e}")


def commit(items, next_id):
    """변경 사항을 파일에 쓰고 화면을 다시 그린다."""
    save_data(items, next_id)
    st.rerun()


# 수정 중인 항목만 화면 상태로 들고 있는다(목록 자체는 파일이 원본).
if "editing_id" not in st.session_state:
    st.session_state.editing_id = None

items, next_id = load_data()

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
    if new_name.strip():
        items.append(
            {"id": next_id, "name": new_name.strip(), "qty": int(new_qty), "done": False}
        )
        commit(items, next_id + 1)
    else:
        st.warning("아이템 이름을 입력해 주세요.")

st.divider()

# ---------- 목록 ----------
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
                    commit(items, next_id)
                else:
                    st.warning("아이템 이름은 비울 수 없습니다.")
            if c4.button("취소", key=f"cancel_{item_id}", use_container_width=True):
                st.session_state.editing_id = None
                st.rerun()

        # 일반 모드
        else:
            c1, c2, c3 = st.columns([6, 1, 1])

            text = f"{item['name']}  ×{item['qty']}"
            label = f"~~{text}~~" if item["done"] else text
            checked = c1.checkbox(label, value=item["done"], key=f"check_{item_id}")
            if checked != item["done"]:
                item["done"] = checked
                commit(items, next_id)

            if c2.button("수정", key=f"edit_{item_id}", use_container_width=True):
                st.session_state.editing_id = item_id
                st.rerun()

            if c3.button("삭제", key=f"del_{item_id}", use_container_width=True):
                remaining = [i for i in items if i["id"] != item_id]
                st.session_state.editing_id = None
                commit(remaining, next_id)

    st.divider()

    done_count = sum(1 for i in items if i["done"])
    st.caption(
        f"전체 {len(items)}개 · 완료 {done_count}개 · 남음 {len(items) - done_count}개"
    )

    b1, b2 = st.columns(2)
    if b1.button("완료 항목 삭제", use_container_width=True):
        st.session_state.editing_id = None
        commit([i for i in items if not i["done"]], next_id)
    if b2.button("전체 삭제", use_container_width=True):
        st.session_state.editing_id = None
        commit([], next_id)

# ---------- 저장 상태 ----------
with st.expander("저장 정보"):
    st.write(f"저장 파일: `{DATA_FILE}`")
    if DATA_FILE.exists():
        saved = datetime.fromtimestamp(DATA_FILE.stat().st_mtime)
        st.write(f"마지막 저장: {saved:%Y-%m-%d %H:%M:%S} · {DATA_FILE.stat().st_size} bytes")
    else:
        st.write("아직 저장된 파일이 없습니다.")
