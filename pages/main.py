from backend import (obtener_datos_contador, interpolar_cuartohoraria_boe, download_esios_id, combinar_consumos_spot, comparativa_mensual, generar_menu,
                     graficar_consumos, graficar_evol_coste, graficar_spot, graficar_costes
)

from datetime import date, datetime
import pandas as pd
import streamlit as st

generar_menu()

usuario = st.secrets['KEY_AXON_USER']
password = st.secrets['KEY_AXON_PASSWORD']

# Cargar suministros desde secrets
suministros = st.secrets["suministros"]
# Crear lista de etiquetas legibles para el selector
labels = [
    f"{data['peaje']} - tipo {data['tipo']}"
    #f"{data['cups']} ({data['peaje']} - tipo {data['tipo']})"
    for data in suministros.values()
]
# Mostrar el selectbox en el sidebar
seleccion_label = st.sidebar.selectbox(
    "Selecciona un suministro:",
    options=labels
)
# Obtener el diccionario correspondiente al suministro elegido
seleccion = list(suministros.values())[labels.index(seleccion_label)]
cups = seleccion['cups']

# Estado para controlar si ya se actualizó manualmente
if "actualizado" not in st.session_state:
    st.session_state.actualizado = False

# Botón con deshabilitado tras actualizar
if st.sidebar.button("🔄 Actualizar datos", disabled=st.session_state.actualizado):
    st.cache_data.clear()
    st.session_state.actualizado = True
    st.success("Datos actualizados correctamente.")
    st.rerun()


#fecha_inicio = '2025-10-01'
#fecha_fin = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')

# --- Generar lista de meses desde octubre 2025 hasta hoy ---
mes_inicio_fijo = datetime(2025, 10, 1)
hoy = date.today()

# Creamos rango de meses (inicio de mes)
fechas_meses = pd.date_range(mes_inicio_fijo, hoy, freq="MS")

# Nombres legibles para el usuario, tipo "Octubre 2025"
nombres_meses = [f.strftime("%B %Y").capitalize() for f in fechas_meses]

# Selectbox con valor actual por defecto
seleccion = st.sidebar.selectbox(
    "📅 Selecciona mes de análisis",
    nombres_meses,
    index=len(nombres_meses) - 1
)

# Obtener fecha seleccionada (inicio del mes)
mes_seleccionado = fechas_meses[nombres_meses.index(seleccion)]

# Calcular inicio y fin del mes
fecha_inicio = mes_seleccionado.date()
fecha_fin = (mes_seleccionado + pd.offsets.MonthEnd(1)).date()


tipo_curva = 'TM2'

df_cch_real, df_ch = obtener_datos_contador(usuario, password, cups, fecha_inicio, fecha_fin, tipo_curva)
df_cch_real_interpol = interpolar_cuartohoraria_boe(df_ch)

#Tabla comparativa con los consumos real e interpolado (CUARTO HORARIO)
df_comp = pd.merge(
    df_cch_real,
    df_cch_real_interpol[["datetime", "consumo_interpolado"]],
    on="datetime",
    how="inner"
)

# Obtenemos spot qh
id = '600'
agregacion = 'average'
agrupacion = 'fifteen_minutes'
df_spot = download_esios_id(id,fecha_inicio,fecha_fin,agrupacion,agregacion)

#Tabla COMPLETA con los costes real e interpolado (CUARTO HORARIO)
df_comp = combinar_consumos_spot(df_comp, df_spot)
#Tabla DIARIA con los costes real e interpolado para ver la evolución mensual
df_comp_diario, mes_nombre = comparativa_mensual(df_comp)

#GRÁFICOS
graf_comp_consumos = graficar_consumos(df_comp)
graf_spot = graficar_spot(df_spot)
graf_comp_costes = graficar_costes(df_comp)
graf_evol_coste = graficar_evol_coste(df_comp_diario, mes_nombre)

#METRIC CONSUMOS
total_consumo_real = df_comp['consumo_real'].sum()
total_consumo_interpol = df_comp['consumo_interpolado'].sum()
diferencia_total_consumo = total_consumo_interpol - total_consumo_real
diferencia_total_consumo_porc = round(diferencia_total_consumo / total_consumo_real,2)

#METRIC SPOT
media_spot = round(df_spot['spot'].mean(),2)
#METRIC COSTE
total_coste_real = round(df_comp['coste_real'].sum(),2)
total_coste_interpol = round(df_comp['coste_interpolado'].sum(),2)
diferencia_total_coste = round(total_coste_interpol - total_coste_real,2)
diferencia_total_coste_porc = round(diferencia_total_coste*100 / total_coste_real,2)


#LAYOUT
c1a, c2a =st.columns(2)

altura_contenedor = 550
with c1a:
    with st.container(height=altura_contenedor):
        st.subheader('1. Comparativa consumos Qh: Real vs Interpolado', divider='rainbow')
        c1a1,c1a2=st.columns([0.8,0.2])
        with c1a1:
            st.plotly_chart(graf_comp_consumos, use_container_width=True)
            
        with c1a2:
            st.metric('Consumo REAL (kWh)', f"{total_consumo_real:,.0f}".replace(",", "."))
            st.metric('Consumo INTERPOLADO (kWh)', f"{total_consumo_interpol:,.0f}".replace(",", "."))
            st.metric('Diferencia consumo (kWh)', diferencia_total_consumo, delta=diferencia_total_consumo_porc)
    
    with st.container(height=altura_contenedor, border=True):
        st.subheader('3. Comparativa costes Qh: Real vs Interpolado', divider='rainbow')
        c1a3,c1a4=st.columns([0.8,0.2])
        with c1a3:
            st.plotly_chart(graf_comp_costes, use_container_width=True)

with c2a:
    with st.container(height=altura_contenedor, border=True):
        st.subheader('2. Precios SPOT cuarto horarios', divider='rainbow')
        c2a1,c2a2=st.columns([0.8,0.2])
        with c2a1:
            st.plotly_chart(graf_spot, use_container_width=True)
        with c2a2:
            st.metric('Precio medio SPOT (€)', f'{media_spot:,.2f}'.replace('.',','))

    with st.container(height=altura_contenedor, border=True):
        st.subheader('4. Evolución diaria y mensual de la diferencia', divider='rainbow')
        c2a3,c2a4=st.columns([0.8,0.2])
        with c2a3:
            st.plotly_chart(graf_evol_coste, use_container_width=True)
        with c2a4:
            st.metric('Coste REAL (€)', f"{total_coste_real:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            st.metric('Coste INTERPOLADO (€)', f"{total_coste_interpol:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            st.metric('Diferencia coste (€)', f'{diferencia_total_coste:,.2f}'.replace(",", "X").replace(".", ",").replace("X", "."), delta=f'{diferencia_total_coste_porc:,.2f}%'.replace(",", "."))
        
    

