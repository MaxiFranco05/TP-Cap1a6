"""Módulo de tareas en segundo plano para órdenes de trabajo."""

from app.modules.ordenes.service import notificar_cliente_orden_terminada

__all__ = ["notificar_cliente_orden_terminada"]
