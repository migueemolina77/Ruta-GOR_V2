import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
from folium.features import DivIcon

# Configuración de página
st.set_page_config(page_title="Logística Rubiales & CASE - Movilización", layout="wide")

# 1. Función para convertir coordenadas (DMS a Decimal o String a Float)
def dms_to_decimal(dms_str):
    try:
        if pd.isna(dms_str) or str(dms_str).strip() == "": return None
        # Si ya es un número o formato decimal simple
        if isinstance(dms_str, (int, float)): return float(dms_str)
        
        # Extraer números del string
        parts = re.findall(r"[-+]?\d*\.\d+|\d+", str(dms_str))
        if len(parts) == 1: return float(parts[0])
        if len(parts) < 3: return None
        
        deg, minu, sec = map(float, parts)
        decimal = deg + (minu / 60) + (sec / 3600)
        # Ajuste para Hemisferio Sur u Oeste
        if any(char in str(dms_str).upper() for char in ['S', 'W', 'O']):
            decimal *= -1
        return decimal
    except:
        return None

# 2. Función para obtener tramos reales mediante OSRM
def obtener_tramo_real(punto_a, punto_b):
    url = f"http://router.project-osrm.org/route/v1/driving/{punto_a['lon']},{punto_a['lat']};{punto_b['lon']},{punto_b['lat']}?overview=full&geometries=geojson"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if data['code'] == 'Ok':
            ruta = data['routes'][0]
            geometria = [[coord[1], coord[0]] for coord in ruta['geometry']['coordinates']]
            distancia_km = ruta['distance'] / 1000
            return geometria, distancia_km
    except:
        pass
    return [], 0

# 3. Carga y limpieza automática por ÍNDICES (Inmune a nombres de columnas)
@st.cache_data
def cargar_base_coordenadas(file_path):
    # Saltamos las primeras 3 filas decorativas del Excel/CSV
    df = pd.read_csv(file_path, skiprows=3, encoding='latin-1')
    
    # Seleccionamos columnas por posición exacta según tu archivo:
    # 0: POZO | 2: Clúster | 5: Este Central | 6: Norte Central | 7: Latitud | 8: Longitud
    df_coords = df.iloc[:, [0, 2, 5, 6, 7, 8]].copy()
    df_coords.columns = ['pozo', 'cluster', 'este', 'norte', 'lat_raw', 'lon_raw']
    
    # Procesamos coordenadas a formato numérico para el mapa
    df_coords['lat_dec'] = df_coords['lat_raw'].apply(dms_to_decimal)
    df_coords['lon_dec'] = df_coords['lon_raw'].apply(dms_to_decimal)
    
    # Aseguramos que Este y Norte sean numéricos para cálculos técnicos
    df_coords['este'] = pd.to_numeric(df_coords['este'], errors='coerce')
    df_coords['norte'] = pd.to_numeric(df_coords['norte'], errors='coerce')
    
    # Agrupamos por Clúster para el itinerario
    df_final = df_coords.dropna(subset=['lat_dec', 'lon_dec']).groupby('cluster').agg({
        'lat_dec': 'first', 
        'lon_dec': 'first', 
        'este': 'first',
        'norte': 'first',
        'pozo': lambda x: ', '.join(x.astype(str))
    }).reset_index()
    
    return df_final

# --- LÓGICA DE LA INTERFAZ ---

st.title("🚜 Plan de Movilización: Rubiales - Caño Sur Este")

colores_tramos = ['#E74C3C', '#2ECC71', '#3498DB', '#F1C40F', '#9B59B6', '#E67E22']

try:
    # El nombre debe coincidir exactamente con tu archivo en el repo
    df_maestro = cargar_base_coordenadas("COORDENADAS_RUB_CASE.csv")

    # Sidebar para entrada de datos
    st.sidebar.header("Orden de Movilización")
    st.sidebar.info("Ingresa los Clústeres (Ej: RB-1 o CASE-01)")
    ruta_input = st.sidebar.text_area("Pega los Clústeres en orden:", placeholder="CASE-01\nRB-162\nCASE-373")
    nombres_ruta = [n.strip().upper() for n in re.split(r'[\n,]+', ruta_input) if n.strip()]

    puntos_ruta = []
    for i, nombre in enumerate(nombres_ruta):
        match = df_maestro[df_maestro['cluster'].astype(str).str.upper() == nombre]
        if not match.empty:
            puntos_ruta.append({
                'orden': i + 1,
                'nombre': nombre, 
                'lat': match.iloc[0]['lat_dec'], 
                'lon': match.iloc[0]['lon_dec'], 
                'pozos': match.iloc[0]['pozo'],
                'este': match.iloc[0]['este']
            })

    # Mapa base
    m = folium.Map(location=[df_maestro['lat_dec'].mean(), df_maestro['lon_dec'].mean()], zoom_start=11)

    if len(puntos_ruta) >= 2:
        resumen_ruta = []
        total_km = 0
        
        for i in range(len(puntos_ruta) - 1):
            p1, p2 = puntos_ruta[i], puntos_ruta[i+1]
            geometria, km = obtener_tramo_real(p1, p2)
            
            if geometria:
                color_asignado = colores_tramos[i % len(colores_tramos)]
                folium.PolyLine(geometria, color=color_asignado, weight=7, opacity=0.8).add_to(m)
                
                total_km += km
                resumen_ruta.append({
                    "Orden": f"{p1['orden']} ➡️ {p2['orden']}",
                    "Trayecto": f"{p1['nombre']} a {p2['nombre']}",
                    "KM": round(km, 2)
                })

        # Tabla de itinerario en el sidebar
        st.sidebar.subheader("Itinerario Detallado")
        st.sidebar.table(resumen_ruta)
        st.sidebar.metric("Distancia Total de Campaña", f"{total_km:.2f} Km")

    # Marcadores en el mapa
    for p in puntos_ruta:
        # Marcador con icono de pozo
        folium.Marker(
            location=[p['lat'], p['lon']],
            popup=f"<b>({p['orden']}) Clúster: {p['nombre']}</b><br>Pozos: {p['pozos']}<br>Este: {p['este']}",
            icon=folium.Icon(color='black', icon='oil-well', prefix='fa')
        ).add_to(m)

        # Etiqueta visual con el número de orden
        folium.map.Marker(
            [p['lat'], p['lon']],
            icon=DivIcon(
                icon_size=(150,36),
                icon_anchor=(7,20),
                html=f'<div style="font-size: 11pt; color: white; background-color: black; border-radius: 50%; width: 25px; height: 25px; display: flex; justify-content: center; align-items: center; border: 2px solid white; font-weight: bold;">{p["orden"]}</div>',
            )
        ).add_to(m)

    # Mostrar el mapa
    st_folium(m, width=1100, height=600, returned_objects=[])

except Exception as e:
    st.error(f"Error al procesar los datos: {e}")
