"""Repara mojibake (texto UTF-8 que foi lido como cp1252/Latin-1) já gravado.

Seguro e idempotente: só altera uma string se, ao revertê-la (cp1252 -> utf-8),
o resultado for UTF-8 válido E diferente do original. Strings corretas como
"básico" não revertem para UTF-8 válido, então NÃO são tocadas — rodar duas
vezes não causa dano.

Uso:
  Local:    python backend/repair_encoding.py
  Railway:  railway run python backend/repair_encoding.py
"""
import sys
from pathlib import Path

# Permite `import app` rodando de qualquer diretório.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import models  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402

# Garante que todas as tabelas existem (idempotente) antes de varrer os dados.
Base.metadata.create_all(bind=engine)


def _fix_str(s: str) -> str:
    try:
        repaired = s.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s  # não é mojibake reversível: mantém intacto
    return repaired if repaired != s else s


def _fix_any(v):
    """Aplica o reparo recursivamente em strings dentro de listas/dicts (JSON)."""
    if isinstance(v, str):
        return _fix_str(v)
    if isinstance(v, list):
        return [_fix_any(x) for x in v]
    if isinstance(v, dict):
        return {k: _fix_any(x) for k, x in v.items()}
    return v


# Colunas de texto / JSON por modelo.
CAMPOS = {
    models.Semana: ["titulo"],
    models.Item: ["titulo", "tags", "video", "links", "docs", "notas"],
    models.Projeto: ["titulo", "descricao", "tags", "links"],
    models.Atividade: ["titulo", "enunciado", "respostas", "feedback", "nota", "assuntos"],
}


def main() -> None:
    db = SessionLocal()
    alterados = 0
    try:
        for modelo, campos in CAMPOS.items():
            for row in db.query(modelo).all():
                mudou = False
                for campo in campos:
                    atual = getattr(row, campo)
                    novo = _fix_any(atual)
                    if novo != atual:
                        setattr(row, campo, novo)
                        mudou = True
                if mudou:
                    alterados += 1
        if alterados:
            db.commit()
        print(f"Reparo concluído. Registros corrigidos: {alterados}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
