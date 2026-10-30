"""In-memory хранилище загруженных документов (одна сессия на процесс).
Повторная загрузка файла с тем же именем заменяет прежнюю версию."""
from __future__ import annotations

from threading import Lock

from .models import Document
from .parsing.classify import parse_document


class Store:
    def __init__(self) -> None:
        self._docs: dict[str, Document] = {}  # ключ — имя файла
        self._lock = Lock()

    def add(self, filename: str, raw: str) -> Document:
        doc = parse_document(filename, raw)
        with self._lock:
            self._docs[filename] = doc
        return doc

    def all(self) -> list[Document]:
        return list(self._docs.values())

    def get(self, doc_id: str) -> Document | None:
        return next((d for d in self._docs.values() if d.id == doc_id), None)

    def delete(self, doc_id: str) -> bool:
        with self._lock:
            for k, d in list(self._docs.items()):
                if d.id == doc_id:
                    del self._docs[k]
                    return True
        return False

    def clear(self) -> None:
        with self._lock:
            self._docs.clear()


store = Store()
