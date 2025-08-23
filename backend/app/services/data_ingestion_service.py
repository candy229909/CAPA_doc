# app/services/data_ingestion_service.py
from typing import List, Optional
from datetime import datetime
from pymilvus import MilvusClient, FieldSchema, CollectionSchema, DataType
from sentence_transformers import SentenceTransformer
from app.models.law_article import LawArticle
import logging

logger = logging.getLogger(__name__)

class DataIngestionService:
    def __init__(self, milvus_uri: str, embedding_model_name: str = 'paraphrase-multilingual-mpnet-base-v2'):
        """
        初始化資料匯入服務
        
        Args:
            milvus_uri: Milvus 連接 URI
            embedding_model_name: 句子嵌入模型名稱
        """
        self.milvus_client = MilvusClient(milvus_uri)
        self.embedding_model = SentenceTransformer(embedding_model_name)
        
    def _get_embedding_dimension(self) -> int:
        """取得嵌入向量維度"""
        # 使用測試文本獲取維度
        test_embedding = self.embedding_model.encode(["測試文本"])
        return test_embedding.shape[1]

    def _get_milvus_schema(self) -> CollectionSchema:
        """根據 LawArticle 模型定義 Milvus Schema"""
        embedding_dim = self._get_embedding_dimension()
        
        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, auto_id=False, max_length=64),
            FieldSchema(name="law_name", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="article_no", dtype=DataType.VARCHAR, max_length=32),
            FieldSchema(name="paragraph_no", dtype=DataType.INT64),
            FieldSchema(name="subitem_no", dtype=DataType.INT64),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=4096),
            FieldSchema(name="version_tag", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="effective_from", dtype=DataType.INT64), # 存為 YYYYMMDD 格式
            FieldSchema(name="effective_to", dtype=DataType.INT64), # 存為 YYYYMMDD 格式，0 表示無結束日期
            FieldSchema(name="source_url", dtype=DataType.VARCHAR, max_length=512), # 增加長度
            FieldSchema(name="tags", dtype=DataType.JSON),
            FieldSchema(name="dense_vec", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim)
        ]

        schema = CollectionSchema(fields, "勞動基準法規資料庫")
        return schema

    def ensure_collection(self, collection_name: str) -> bool:
        """
        確保 Milvus Collection 存在並載入
        
        Args:
            collection_name: Collection 名稱
            
        Returns:
            bool: 是否成功創建或載入
        """
        try:
            if not self.milvus_client.has_collection(collection_name):
                schema = self._get_milvus_schema()
                self.milvus_client.create_collection(
                    collection_name=collection_name,
                    schema=schema
                )
                logger.info(f"成功創建 Collection: {collection_name}")
            
            # 載入 Collection（如果尚未載入）
            self.milvus_client.load_collection(collection_name)
            logger.info(f"Collection {collection_name} 已載入")
            return True
            
        except Exception as e:
            logger.error(f"創建或載入 Collection 失敗: {e}")
            return False

    def _convert_date_to_timestamp(self, date_obj: Optional[datetime]) -> int:
        """將日期轉換為 YYYYMMDD 格式的整數"""
        if date_obj is None:
            return 0
        return int(date_obj.strftime("%Y%m%d"))

    def batch_ingest(self, articles: List[LawArticle], collection_name: str) -> bool:
        """
        將多個法規條文物件匯入 Milvus
        
        Args:
            articles: LawArticle 物件列表
            collection_name: 目標 Collection 名稱
            
        Returns:
            bool: 是否匯入成功
        """
        if not articles:
            logger.warning("沒有提供任何文章進行匯入")
            return False
            
        try:
            # 確保 Collection 存在
            if not self.ensure_collection(collection_name):
                return False
            
            # 批量計算嵌入向量
            texts = [article.text for article in articles]
            logger.info(f"開始計算 {len(texts)} 條文章的嵌入向量...")
            vectors = self.embedding_model.encode(texts, batch_size=32, show_progress_bar=True)

            # 準備資料實體
            entities = []
            for i, article in enumerate(articles):
                entity = {
                    "id": article.id,
                    "law_name": article.law_name,
                    "article_no": article.article_no,
                    "paragraph_no": article.paragraph_no,
                    "subitem_no": article.subitem_no,
                    "text": article.text,
                    "version_tag": article.version_tag,
                    "effective_from": self._convert_date_to_timestamp(article.effective_from),
                    "effective_to": self._convert_date_to_timestamp(article.effective_to),
                    "source_url": article.source_url,
                    "tags": article.tags,
                    "dense_vec": vectors[i].tolist()
                }
                entities.append(entity)

            # 批量插入資料
            result = self.milvus_client.insert(collection_name=collection_name, data=entities)
            logger.info(f"成功匯入 {len(entities)} 條法規條文至 {collection_name}")
            
            return True
            
        except Exception as e:
            logger.error(f"批量匯入失敗: {e}")
            return False

    def delete_by_ids(self, collection_name: str, ids: List[str]) -> bool:
        """
        根據 ID 刪除條文
        
        Args:
            collection_name: Collection 名稱
            ids: 要刪除的 ID 列表
            
        Returns:
            bool: 是否刪除成功
        """
        try:
            expr = f"id in {ids}"
            result = self.milvus_client.delete(collection_name=collection_name, expr=expr)
            logger.info(f"成功刪除 {len(ids)} 條記錄")
            return True
            
        except Exception as e:
            logger.error(f"刪除記錄失敗: {e}")
            return False

    def close(self):
        """關閉連接"""
        if hasattr(self.milvus_client, 'close'):
            self.milvus_client.close()
            logger.info("Milvus 連接已關閉")