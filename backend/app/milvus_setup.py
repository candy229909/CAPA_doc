import os
import logging
from pymilvus import connections

logger = logging.getLogger(__name__)

def connect_lite():
    """優先連線外部 URI；否則啟動 Milvus Lite。"""
    uri = os.getenv("MILVUS_URI")
    if uri:
        connections.connect(alias="default", uri=uri)
        logger.info("Milvus connected via MILVUS_URI=%s", uri)
        return

    try:
        from milvus import default_server  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Milvus Lite 未安裝。請 `pip install \"milvus[client]\"` 後重試，"
            "或改用外部 Server：設定 MILVUS_MODE=server 並在 Docker/Compose 啟動 milvus 服務。"
        ) from e

    base_dir = os.getenv("MILVUS_LITE_DIR", "/data/milvus")
    os.makedirs(base_dir, exist_ok=True)
    try:
        default_server.set_base_dir(base_dir)
    except Exception:
        pass

    if not getattr(default_server, "started", False):
        default_server.start()
    connections.connect(alias="default", host="127.0.0.1", port=default_server.listen_port)
    logger.info("Milvus Lite started at 127.0.0.1:%s (base=%s)", default_server.listen_port, base_dir)

def ensure_collection(
    name: str,
    dim: int,
    metric: str,
    text_field: str,
    meta_field: str,
    emb_field: str,
    auto_id: bool = True,
) -> "Collection":
    """建立/取得向量集合，**包含主鍵欄位**。

    必要欄位：
    - id: INT64, is_primary=True, auto_id 依參數
    - {text_field}: VARCHAR（長度預設 8192，可用 MILVUS_TEXT_MAXLEN 覆蓋）
    - {meta_field}: JSON
    - {emb_field}: FLOAT_VECTOR(dim)
    """
    from pymilvus import FieldSchema, CollectionSchema, DataType, Collection, utility

    if utility.has_collection(name):
        coll = Collection(name)
        return coll

    # ---- Fields ----
    text_maxlen = int(os.getenv("MILVUS_TEXT_MAXLEN", "8192"))
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=auto_id),
        FieldSchema(name=text_field, dtype=DataType.VARCHAR, max_length=text_maxlen),
        FieldSchema(name=meta_field, dtype=DataType.JSON),
        FieldSchema(name=emb_field, dtype=DataType.FLOAT_VECTOR, dim=dim),
    ]
    schema = CollectionSchema(fields=fields, description="docs")

    coll = Collection(name=name, schema=schema)

    # ---- Index ----
    metric_type = (metric or "COSINE").upper()
    index_type = os.getenv("MILVUS_INDEX_TYPE", "IVF_FLAT").upper()  # 與搜尋 param 的 nprobe 相容
    if index_type == "AUTOINDEX":
        coll.create_index(emb_field, {"index_type": "AUTOINDEX", "metric_type": metric_type})
    elif index_type == "HNSW":
        coll.create_index(emb_field, {"index_type": "HNSW", "metric_type": metric_type, "params": {"M": 8, "efConstruction": 64}})
    else:
        # 預設 IVF_FLAT；你在 search 用的是 nprobe=10，這個路線最相容
        nlist = int(os.getenv("MILVUS_NLIST", "1024"))
        coll.create_index(emb_field, {"index_type": "IVF_FLAT", "metric_type": metric_type, "params": {"nlist": nlist}})

    coll.load()
    return coll

def connect_server():
    host = os.getenv("MILVUS_HOST", "milvus-1")  # 依你的 compose 服務名；若叫 milvus 就改成 milvus
    port = os.getenv("MILVUS_PORT", "19530")
    connections.connect(alias="default", host=host, port=port)
    logger.info("Milvus Server connected: %s:%s", host, port)

def connect_auto():
    mode = os.getenv("MILVUS_MODE", "server").lower().strip()
    if mode == "lite":
        connect_lite()
    else:
        connect_server()
