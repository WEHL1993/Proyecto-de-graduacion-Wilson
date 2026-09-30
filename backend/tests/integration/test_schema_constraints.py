"""Verifica contra PostgreSQL real las restricciones críticas del esquema (sección 3.3).

Requiere la BD migrada (`make migrate`); si no hay conexión, las pruebas se omiten.
Cada prueba corre dentro de una transacción que se revierte al final.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.database import get_engine


@pytest.fixture
def conn():
    try:
        connection = get_engine().connect()
    except (OperationalError, UnicodeDecodeError):  # psycopg2 en Windows
        pytest.skip("PostgreSQL no disponible")
    trans = connection.begin()
    try:
        yield connection
    finally:
        trans.rollback()
        connection.close()


@pytest.fixture
def base_ids(conn):
    """Crea el mínimo de datos maestros: usuario, categoría, producto, ruta y modelo productivo."""
    q = lambda sql: conn.execute(text(sql)).scalar_one()  # noqa: E731
    ids = {
        "usuario": q(
            "INSERT INTO usuarios (email, password_hash, nombre_completo) "
            "VALUES ('test@ds.gt', 'x', 'Test') RETURNING id"
        ),
        "categoria": q("INSERT INTO categorias (nombre) VALUES ('Bebidas') RETURNING id"),
    }
    ids["producto"] = q(
        f"INSERT INTO productos (sku, nombre, categoria_id) "
        f"VALUES ('BEB-0034', 'Gaseosa 2L', '{ids['categoria']}') RETURNING id"
    )
    ids["ruta"] = q("INSERT INTO rutas (codigo, nombre) VALUES ('R-04', 'Escuintla') RETURNING id")
    ids["modelo"] = q(
        "INSERT INTO modelos_ml (nombre, algoritmo, version, estado, ruta_artefacto,"
        " hash_artefacto,"
        " hiperparametros, esquema_features, ventana_desde, ventana_hasta, motivo_entrenamiento,"
        " promovido_en) VALUES ('demanda_diaria', 'xgboost', 'v1.0.0', 'produccion', 'x',"
        " repeat('a', 64), '{}', '[]', '2025-01-01', '2025-03-31', 'manual', now()) RETURNING id"
    )
    return ids


def _nueva_carga(conn, ids, fecha="2026-10-01", estado="borrador"):
    return conn.execute(
        text(
            "INSERT INTO cargas_ruta (ruta_id, fecha_operacion, estado, modelo_id, generado_por) "
            "VALUES (:r, :f, :e, :m, :u) RETURNING id"
        ),
        {"r": ids["ruta"], "f": fecha, "e": estado, "m": ids["modelo"], "u": ids["usuario"]},
    ).scalar_one()


def _detalle(conn, carga_id, producto_id, predicha, stock, sugerida, aprobada=None):
    conn.execute(
        text(
            "INSERT INTO detalle_cargas (carga_id, producto_id, cantidad_predicha,"
            " stock_disponible_al_generar, cantidad_sugerida, cantidad_aprobada)"
            " VALUES (:c, :p, :pr, :st, :su, :ap)"
        ),
        {
            "c": carga_id,
            "p": producto_id,
            "pr": predicha,
            "st": stock,
            "su": sugerida,
            "ap": aprobada,
        },
    )


def test_sugerida_es_min_demanda_stock(conn, base_ids):
    carga = _nueva_carga(conn, base_ids)
    _detalle(conn, carga, base_ids["producto"], predicha=210, stock=150, sugerida=150)  # válido
    with pytest.raises(IntegrityError, match="sugerida_min_demanda_stock"):
        with conn.begin_nested():
            _detalle(
                conn,
                _nueva_carga(conn, base_ids, "2026-10-02"),
                base_ids["producto"],
                210,
                150,
                210,
            )


def test_aprobada_no_excede_stock(conn, base_ids):
    carga = _nueva_carga(conn, base_ids)
    with pytest.raises(IntegrityError, match="aprobada_no_excede_stock"):
        with conn.begin_nested():
            _detalle(conn, carga, base_ids["producto"], 210, 150, 150, aprobada=200)


def test_una_carga_vigente_por_ruta_y_dia(conn, base_ids):
    _nueva_carga(conn, base_ids, estado="borrador")
    with pytest.raises(IntegrityError, match="uq_cargas_ruta_vigente_ruta_fecha"):
        with conn.begin_nested():
            _nueva_carga(conn, base_ids, estado="borrador")
    # Una rechazada no ocupa el cupo vigente.
    _nueva_carga(conn, base_ids, fecha="2026-10-05", estado="rechazada")
    _nueva_carga(conn, base_ids, fecha="2026-10-05", estado="borrador")


def test_un_solo_modelo_en_produccion(conn, base_ids):
    with pytest.raises(IntegrityError, match="uq_modelos_ml_produccion_nombre"):
        with conn.begin_nested():
            conn.execute(
                text(
                    "INSERT INTO modelos_ml (nombre, algoritmo, version, estado, ruta_artefacto,"
                    " hash_artefacto, hiperparametros, esquema_features, ventana_desde,"
                    " ventana_hasta, motivo_entrenamiento, promovido_en) VALUES ('demanda_diaria',"
                    " 'lstm', 'v2.0.0', 'produccion', 'x', repeat('b', 64), '{}', '[]',"
                    " '2025-01-01', '2025-03-31', 'manual', now())"
                )
            )


def test_ventas_idempotentes_sin_vendedor(conn, base_ids):
    lote = conn.execute(
        text(
            "INSERT INTO etl_lotes (usuario_id, archivo_nombre, checksum_sha256)"
            " VALUES (:u, 'ventas.xlsx', repeat('c', 64)) RETURNING id"
        ),
        {"u": base_ids["usuario"]},
    ).scalar_one()
    insert = text(
        "INSERT INTO ventas_historicas (lote_id, fecha_venta, producto_id, ruta_id, vendedor_id,"
        " cantidad, precio_unitario, monto_total)"
        " VALUES (:l, '2025-03-01', :p, :r, NULL, 2, 61, 122)"
        " ON CONFLICT ON CONSTRAINT uq_ventas_historicas_fecha_producto_ruta_vendedor DO NOTHING"
    )
    params = {"l": lote, "p": base_ids["producto"], "r": base_ids["ruta"]}
    conn.execute(insert, params)
    conn.execute(insert, params)  # re-carga: no debe duplicar aunque vendedor_id sea NULL
    total = conn.execute(text("SELECT count(*) FROM ventas_historicas")).scalar_one()
    assert total == 1
