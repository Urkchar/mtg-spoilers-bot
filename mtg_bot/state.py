import json, os, tempfile
from typing import TypedDict

class StateDict(TypedDict, total=False):
    last_run_date: str | None
    posted_ids: list[str]

def _default_state() -> StateDict:
    return {"last_run_date": None, "posted_ids": []}

def load_state(path: str) -> StateDict:
    if not os.path.exists(path):
        return _default_state()
    try:
        with open(path, "r", encoding="utf-8") as f:
            st = json.load(f)
        if not isinstance(st, dict):
            return _default_state()
        st.setdefault("last_run_date", None)
        st.setdefault("posted_ids", [])
        if not isinstance(st["posted_ids"], list):
            st["posted_ids"] = []
        return st  # type: ignore[return-value]
    except Exception:
        return _default_state()

def save_state_atomic(path: str, payload: StateDict) -> None:
    dirpath = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmpname = tempfile.mkstemp(dir=dirpath, prefix=".tmp_state_", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as wf:
            json.dump(payload, wf, ensure_ascii=False, indent=2)
            wf.flush()
            os.fsync(wf.fileno())
        os.replace(tmpname, path)
    finally:
        try:
            if os.path.exists(tmpname):
                os.remove(tmpname)
        except Exception:
            pass

def has_been_posted(state: StateDict, card: dict) -> bool:
    cid = card.get("id")
    return cid is not None and cid in (state.get("posted_ids") or [])

def persist_posted(path: str, state: StateDict, card: dict) -> StateDict:
    cid = card.get("id")
    if not cid:
        return state
    # reload to avoid losing progress if other process edited it
    current = load_state(path)
    if cid not in current["posted_ids"]:
        current["posted_ids"].append(cid)
        save_state_atomic(path, current)
    # keep caller's in-memory state in sync
    if cid not in state["posted_ids"]:
        state["posted_ids"].append(cid)
    return state
