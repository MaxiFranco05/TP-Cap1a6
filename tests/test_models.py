from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import DateTime, Numeric
from sqlalchemy.orm import configure_mappers
from sqlmodel import SQLModel


def test_usuarios_models_columns_and_types() -> None:
    from app.modules.usuarios.models import (
        AsignacionRol,
        EventoSeguridad,
        IntentoAcceso,
        Usuario,
    )

    tables = SQLModel.metadata.tables
    assert "usuario" in tables
    assert "asignacion_rol" in tables
    assert "intento_acceso" in tables
    assert "evento_seguridad" in tables

    # 1. usuario
    t_usuario = tables["usuario"]
    assert set(t_usuario.columns.keys()) >= {
        "id",
        "email",
        "nombre",
        "password_hash",
        "activo",
        "debe_cambiar_password",
        "password_cambiada_en",
    }
    assert t_usuario.c.email.unique or any(
        ix.unique and [c.name for c in ix.columns] == ["email"] for ix in t_usuario.indexes
    )
    assert isinstance(t_usuario.c.password_cambiada_en.type, DateTime)
    assert t_usuario.c.password_cambiada_en.type.timezone is True
    assert t_usuario.c.password_cambiada_en.nullable is True

    # 2. asignacion_rol
    t_rol = tables["asignacion_rol"]
    assert set(t_rol.columns.keys()) >= {
        "id",
        "usuario_id",
        "rol",
        "desde",
        "vence_en",
        "revocada_en",
        "otorgada_por",
    }
    for col_name in ("desde", "vence_en", "revocada_en"):
        col_type = t_rol.c[col_name].type
        assert isinstance(col_type, DateTime) and col_type.timezone is True

    indexed_cols_rol = {tuple(c.name for c in ix.columns) for ix in t_rol.indexes}
    assert ("usuario_id",) in indexed_cols_rol
    assert ("otorgada_por",) in indexed_cols_rol

    partial_rol_indexes = [
        ix
        for ix in t_rol.indexes
        if ix.unique
        and [c.name for c in ix.columns] == ["usuario_id", "rol"]
        and "revocada_en IS NULL" in str(ix.dialect_options.get("postgresql", {}).get("where", ""))
    ]
    assert len(partial_rol_indexes) == 1

    check_texts_rol = [
        str(c.sqltext) for c in t_rol.constraints if hasattr(c, "sqltext")
    ]
    assert any(
        all(r in txt for r in ("ADMIN", "RECEPCION", "MECANICO", "CLIENTE"))
        for txt in check_texts_rol
    )

    # 3. intento_acceso
    t_intento = tables["intento_acceso"]
    assert set(t_intento.columns.keys()) >= {"id", "cuando", "email", "ip", "exito"}
    assert isinstance(t_intento.c.cuando.type, DateTime)
    assert t_intento.c.cuando.type.timezone is True
    indexed_cols_intento = {tuple(c.name for c in ix.columns) for ix in t_intento.indexes}
    assert ("email", "ip", "cuando") in indexed_cols_intento

    # 4. evento_seguridad
    t_evento = tables["evento_seguridad"]
    assert set(t_evento.columns.keys()) >= {"id", "cuando", "actor", "accion"}
    assert isinstance(t_evento.c.cuando.type, DateTime)
    assert t_evento.c.cuando.type.timezone is True


def test_clientes_models_columns_constraints_and_navigation() -> None:
    from app.modules.clientes.models import Cliente, Vehiculo

    tables = SQLModel.metadata.tables
    assert "cliente" in tables
    assert "vehiculo" in tables

    # 5. cliente
    t_cliente = tables["cliente"]
    assert set(t_cliente.columns.keys()) >= {
        "id",
        "usuario_id",
        "nombre",
        "documento",
        "telefono",
    }
    assert t_cliente.c.usuario_id.nullable is True
    assert t_cliente.c.usuario_id.unique or any(
        ix.unique and [c.name for c in ix.columns] == ["usuario_id"] for ix in t_cliente.indexes
    )
    assert t_cliente.c.documento.unique or any(
        ix.unique and [c.name for c in ix.columns] == ["documento"] for ix in t_cliente.indexes
    )

    # 6. vehiculo
    t_vehiculo = tables["vehiculo"]
    assert set(t_vehiculo.columns.keys()) >= {
        "id",
        "cliente_id",
        "patente",
        "marca",
        "modelo",
        "anio",
        "borrado_en",
    }
    assert isinstance(t_vehiculo.c.borrado_en.type, DateTime)
    assert t_vehiculo.c.borrado_en.type.timezone is True
    assert t_vehiculo.c.borrado_en.nullable is True

    indexed_cols_veh = {tuple(c.name for c in ix.columns) for ix in t_vehiculo.indexes}
    assert ("cliente_id",) in indexed_cols_veh

    partial_veh_indexes = [
        ix
        for ix in t_vehiculo.indexes
        if ix.unique
        and [c.name for c in ix.columns] == ["patente"]
        and "borrado_en IS NULL" in str(ix.dialect_options.get("postgresql", {}).get("where", ""))
    ]
    assert len(partial_veh_indexes) == 1

    check_texts_veh = [
        str(c.sqltext) for c in t_vehiculo.constraints if hasattr(c, "sqltext")
    ]
    assert any("1950" in txt and "2100" in txt for txt in check_texts_veh)


def test_repuestos_and_ordenes_models_and_full_mapper_configuration() -> None:
    from app.modules.clientes.models import Cliente, Vehiculo
    from app.modules.ordenes.models import (
        EstadoOrden,
        HistorialEstadoOrden,
        ItemOrden,
        OrdenTrabajo,
    )
    from app.modules.repuestos.models import (
        HistorialPrecioRepuesto,
        MovimientoStock,
        Repuesto,
    )
    from app.modules.usuarios.models import Usuario

    configure_mappers()

    # Check 1:1 navigation on Usuario.cliente
    mapper_usuario = Usuario.__mapper__
    assert "cliente" in mapper_usuario.relationships
    assert mapper_usuario.relationships["cliente"].uselist is False

    tables = SQLModel.metadata.tables
    assert set(tables.keys()) == {
        "usuario",
        "asignacion_rol",
        "intento_acceso",
        "evento_seguridad",
        "cliente",
        "vehiculo",
        "repuesto",
        "movimiento_stock",
        "historial_precio_repuesto",
        "estado_orden",
        "orden_trabajo",
        "item_orden",
        "historial_estado_orden",
    }

    # 7. repuesto
    t_rep = tables["repuesto"]
    assert set(t_rep.columns.keys()) >= {
        "id",
        "codigo",
        "descripcion",
        "precio",
        "stock",
        "borrado_en",
    }
    assert isinstance(t_rep.c.precio.type, Numeric)
    assert (t_rep.c.precio.type.precision, t_rep.c.precio.type.scale) == (10, 2)
    assert isinstance(t_rep.c.borrado_en.type, DateTime) and t_rep.c.borrado_en.type.timezone is True

    partial_rep_indexes = [
        ix
        for ix in t_rep.indexes
        if ix.unique
        and [c.name for c in ix.columns] == ["codigo"]
        and "borrado_en IS NULL" in str(ix.dialect_options.get("postgresql", {}).get("where", ""))
    ]
    assert len(partial_rep_indexes) == 1

    # 8. estado_orden
    t_estado = tables["estado_orden"]
    assert set(t_estado.columns.keys()) >= {"codigo", "descripcion", "posicion", "es_final"}
    assert [c.name for c in t_estado.primary_key.columns] == ["codigo"]
    assert t_estado.c.posicion.unique or any(
        ix.unique and [c.name for c in ix.columns] == ["posicion"] for ix in t_estado.indexes
    )

    # 9. orden_trabajo
    t_orden = tables["orden_trabajo"]
    assert set(t_orden.columns.keys()) >= {
        "id",
        "vehiculo_id",
        "mecanico_id",
        "estado",
        "falla",
        "creada_en",
        "total",
    }
    assert isinstance(t_orden.c.total.type, Numeric)
    assert (t_orden.c.total.type.precision, t_orden.c.total.type.scale) == (12, 2)
    assert isinstance(t_orden.c.creada_en.type, DateTime) and t_orden.c.creada_en.type.timezone is True
    indexed_cols_orden = {tuple(c.name for c in ix.columns) for ix in t_orden.indexes}
    assert ("vehiculo_id",) in indexed_cols_orden
    assert ("mecanico_id",) in indexed_cols_orden
    assert ("estado",) in indexed_cols_orden

    # 10. item_orden
    t_item = tables["item_orden"]
    assert set(t_item.columns.keys()) >= {
        "id",
        "orden_id",
        "repuesto_id",
        "cantidad",
        "precio_unitario",
    }
    assert isinstance(t_item.c.precio_unitario.type, Numeric)
    assert (t_item.c.precio_unitario.type.precision, t_item.c.precio_unitario.type.scale) == (10, 2)
    indexed_cols_item = {tuple(c.name for c in ix.columns) for ix in t_item.indexes}
    assert ("orden_id",) in indexed_cols_item
    assert ("repuesto_id",) in indexed_cols_item

    # 11. historial_estado_orden
    t_hist_est = tables["historial_estado_orden"]
    assert set(t_hist_est.columns.keys()) >= {
        "id",
        "orden_id",
        "desde_estado",
        "hasta_estado",
        "usuario_id",
        "cuando",
    }
    assert isinstance(t_hist_est.c.cuando.type, DateTime) and t_hist_est.c.cuando.type.timezone is True
    indexed_cols_hist_est = {tuple(c.name for c in ix.columns) for ix in t_hist_est.indexes}
    for fk_col in ("orden_id", "desde_estado", "hasta_estado", "usuario_id"):
        assert (fk_col,) in indexed_cols_hist_est

    # 12. movimiento_stock
    t_mov = tables["movimiento_stock"]
    assert set(t_mov.columns.keys()) >= {
        "id",
        "repuesto_id",
        "orden_id",
        "usuario_id",
        "cantidad",
        "motivo",
        "cuando",
    }
    assert isinstance(t_mov.c.cuando.type, DateTime) and t_mov.c.cuando.type.timezone is True
    indexed_cols_mov = {tuple(c.name for c in ix.columns) for ix in t_mov.indexes}
    for fk_col in ("repuesto_id", "orden_id", "usuario_id"):
        assert (fk_col,) in indexed_cols_mov

    # 13. historial_precio_repuesto
    t_hist_prec = tables["historial_precio_repuesto"]
    assert set(t_hist_prec.columns.keys()) >= {
        "id",
        "repuesto_id",
        "usuario_id",
        "precio_anterior",
        "precio_nuevo",
        "cuando",
    }
    assert isinstance(t_hist_prec.c.precio_anterior.type, Numeric)
    assert isinstance(t_hist_prec.c.precio_nuevo.type, Numeric)
    assert isinstance(t_hist_prec.c.cuando.type, DateTime) and t_hist_prec.c.cuando.type.timezone is True
    indexed_cols_prec = {tuple(c.name for c in ix.columns) for ix in t_hist_prec.indexes}
    for fk_col in ("repuesto_id", "usuario_id"):
        assert (fk_col,) in indexed_cols_prec
