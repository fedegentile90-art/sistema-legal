# Manual Operativo - Rol Abogado

Fecha de referencia: 2026-02-13

## 1) Inicio rapido

1. Abrir la app con `RUN_ERP.cmd` o `python -m streamlit run app.py`.
2. Si usas Windows, crear acceso directo desde `Configuracion > Operativo > Crear acceso directo en Escritorio`.
3. Verificar que el auto-guardado este activo en `Configuracion > Operativo` para edicion diaria.
4. Verificar tema/densidad:
   - El sistema recuerda el ultimo tema y densidad por usuario autenticado.
   - Si el equipo desactiva el rediseño (`VG_UI_REVAMP_V2=0`), vuelve al shell visual previo.
5. En la barra lateral usar rutas primarias:
   - `Dashboard`
   - `Gestion`
   - `Agenda`
   - `Finanzas`
   - `Auditoria`
   - `Configuracion`

## 2) Alta y edicion de casos (Gestion)

### Alta de caso

1. Ir a `Gestion`.
2. Seccion `Casos`, modo `Listado`.
3. Usar accion de alta de caso y completar datos base:
   - anio, estado, cliente, fuero, causa.
4. Guardar y verificar que el caso aparece en la grilla.

### Edicion de caso

1. En `Gestion > Casos`, seleccionar un caso.
2. Cambiar a modo `Editar`.
3. Completar/ajustar campos juridicos:
   - `EXPEDIENTE`, `CARATULA`, `RESPONSABLE`, `CONTROL`,
   - `EVENTO`, `FECHA_EVENTO`,
   - `TAREA_PENDIENTE`, `FECHA_TAREA`,
   - `OBSERVACIONES`.
4. Guardar y confirmar retorno a detalle sin errores.

### Recomendacion operativa

- Usar el wizard de minimos para normalizar casos legacy antes de agenda diaria.

## 3) Agenda diaria (Agenda)

1. Ir a `Agenda`.
2. Revisar primero vencidas y proximas.
3. Si la agenda aparece vacia por filtros:
   - usar `Limpiar filtros`.
4. Ejecutar seguimiento diario:
   - tareas vencidas;
   - tareas proximas (7/30 dias);
   - responsable asignado.

## 4) Carga financiera (Finanzas)

### Carga puntual

1. Ir a `Finanzas`.
2. Seleccionar caso.
3. Completar/editar:
   - `MONTO_DEMANDADO`
   - `HONORARIOS_PACTADOS`
   - `ESTADO_PAGO`
4. Guardar.

### Carga masiva por CSV (coordinada con Administracion)

1. Ir a `Finanzas`.
2. Usar importador CSV.
3. Correr `dry-run` para validar filas.
4. Revisar reporte por fila (errores/omitidos/actualizados).
5. Aplicar importacion solo cuando `dry-run` sea consistente.

## 5) Auditoria y control de calidad

1. Ir a `Auditoria`.
2. Ejecutar auditoria manual desde el boton `Ejecutar auditoria`.
3. Revisar:
   - resumen de errores/warnings/info;
   - tabla de hallazgos;
   - KPI operativo;
   - tendencia diaria.
4. Priorizar correcciones de:
   - `DATA-050` (faltantes minimos),
   - fechas invalidas,
   - datos juridicos incompletos que afectan agenda/control.

## 6) Cierre diario sugerido

1. Casos criticos actualizados.
2. Agenda del dia siguiente revisada.
3. Datos financieros del dia cargados o informados.
4. Auditoria ejecutada y hallazgos criticos registrados.
