import streamlit as st
import pandas as pd
import pyodbc
import plotly.graph_objects as go

# --- 1. CONFIGURAÇÃO DE ACESSO ---
usuarios_bi = {
    "Comercial": "comercial@2026",
    "Producao": "@producao2026",
    "Instalacao": "inst@2026",
    "Administrativo": "adm2026@",
    "Compras": "compras2026@",
    "Qualidade": "@qualidade2026",
    "Diretoria": "diretoria2026"
}

mapa_centros = {
    "Comercial": "COM",
    "Producao": "PRD",
    "Instalacao": "INST",
    "Administrativo": "ADM",
    "Compras": "COMP",
    "Qualidade": "QUAL"
}

# --- 2. FUNÇÃO DE CONSULTA ---
def buscar_dados_sap(setor, ano):
    conn_str = (
        'DRIVER={HDBODBC};'
        'SERVERNODE=hanab1:30015;'
        'UID=SYSTEM;'
        'PWD=Sigpel@2991;'
        'DATABASENAME=NDB;'
    )
    try:
        conn = pyodbc.connect(conn_str)
        
        # Lógica de filtro: Se for Diretoria, traz tudo. Se não, filtra pelo mapa_centros.
        filtro_cc = "" if setor == "Diretoria" else f"AND T2.\"OcrCode\" = '{mapa_centros.get(setor)}'"
        
        query = f'''
        SELECT
            T0."AcctCode" AS "Codigo Conta",
            T3."AcctName" AS "Nome da Conta",
            CASE T0."Line_ID"
                WHEN 0 THEN 'Jan' WHEN 1 THEN 'Fev' WHEN 2 THEN 'Mar'
                WHEN 3 THEN 'Abr' WHEN 4 THEN 'Mai' WHEN 5 THEN 'Jun'
                WHEN 6 THEN 'Jul' WHEN 7 THEN 'Ago' WHEN 8 THEN 'Set'
                WHEN 9 THEN 'Out' WHEN 10 THEN 'Nov' WHEN 11 THEN 'Dez'
            END AS "Mês",
            T0."Line_ID" as "Mes_Num",
            SUM(CAST((T0."DebLTotal" - T0."CredLTotal") AS DECIMAL(19,2))) AS "Orcado",
            SUM(CAST((
                SELECT IFNULL(SUM(J0."Debit" - J0."Credit"), 0)
                FROM "SBO_SIGPEL_TST".JDT1 J0
                WHERE J0."Account" = T0."AcctCode"
                  AND J0."ProfitCode" = T2."OcrCode"
                  AND MONTH(J0."RefDate") = (T0."Line_ID" + 1)
                  AND YEAR(J0."RefDate") = {ano}
                  AND J0."TransType" <> -2
            ) AS DECIMAL(19,2))) AS "Realizado"
        FROM "SBO_SIGPEL_TST".BGT1 T0
        INNER JOIN "SBO_SIGPEL_TST".OBGS T2 ON T0."Instance" = T2."AbsId"
        INNER JOIN "SBO_SIGPEL_TST".OACT T3 ON T0."AcctCode" = T3."AcctCode"
        WHERE YEAR(T2."FinancYear") = {ano}
          {filtro_cc}
          AND (T0."DebLTotal" - T0."CredLTotal") <> 0
        GROUP BY T0."AcctCode", T3."AcctName", T0."Line_ID"
        ORDER BY T0."AcctCode", T0."Line_ID"
        '''
        df = pd.read_sql(query, conn)
        conn.close()
        df['Diferença'] = df['Orcado'] - df['Realizado']
        return df
    except Exception as e:
        st.error(f"Erro SAP: {e}")
        return pd.DataFrame()

# --- 3. INTERFACE ---
st.set_page_config(page_title="SIGPEL - BI Orçamentário", layout="wide")

if 'logado' not in st.session_state:
    st.session_state.logado = False

if not st.session_state.logado:
    st.title("🚀 BI Orçamentário SIGPEL")
    col1, _ = st.columns([1, 1])
    with col1:
        setor_input = st.selectbox("Selecione seu Perfil", list(usuarios_bi.keys()))
        senha_input = st.text_input("Senha", type="password")
        if st.button("Acessar Painel"):
            if senha_input == usuarios_bi[setor_input]:
                st.session_state.logado = True
                st.session_state.setor = setor_input
                st.rerun()
            else:
                st.error("Senha incorreta.")
else:
    # Sidebar
    st.sidebar.title(f"👤 {st.session_state.setor}")
    ano_sel = st.sidebar.selectbox("Ano Fiscal", [2024, 2025, 2026], index=2)
    
    if st.sidebar.button("Sair / Logoff"):
        st.session_state.logado = False
        st.rerun()

    # Título Dinâmico
    st.title(f"📊 Painel {'Corporativo' if st.session_state.setor == 'Diretoria' else 'Setorial'}")
    
    with st.spinner('Carregando dados do SAP HANA...'):
        df = buscar_dados_sap(st.session_state.setor, ano_sel)

    if not df.empty:
        # KPIs
        t_orc, t_real = df['Orcado'].sum(), df['Realizado'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Orçado Total", f"R$ {t_orc:,.2f}")
        c2.metric("Realizado Total", f"R$ {t_real:,.2f}")
        c3.metric("Saldo Disponível", f"R$ {(t_orc - t_real):,.2f}")

        # --- GRÁFICO COMBINADO: BARRAS (REALIZADO) + LINHA (ORÇADO) ---
        st.subheader("📈 Evolução Mensal: Realizado vs Orçado")
        
        df_mensal = df.groupby(['Mes_Num', 'Mês'])[['Orcado', 'Realizado']].sum().reset_index().sort_values('Mes_Num')

        fig_combo = go.Figure()

        # Adiciona o Realizado como Barras
        fig_combo.add_trace(go.Bar(
            x=df_mensal['Mês'],
            y=df_mensal['Realizado'],
            name='Gasto Realizado',
            marker_color='#e74c3c',
            opacity=0.8
        ))

        # Adiciona o Orçado como Linha
        fig_combo.add_trace(go.Scatter(
            x=df_mensal['Mês'],
            y=df_mensal['Orcado'],
            name='Limite Orçado',
            line=dict(color='#3498db', width=4),
            mode='lines+markers'
        ))

        fig_combo.update_layout(
            xaxis_title="Meses",
            yaxis_title="Valor (R$)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="x unified"
        )

        st.plotly_chart(fig_combo, use_container_width=True)
        
        # --- TABELA DETALHADA ---
        st.subheader("📑 Detalhamento por Conta")
        busca = st.text_input("🔍 Buscar por Nome da Conta Contábil")
        
        df_filtered = df[df['Nome da Conta'].str.contains(busca, case=False)]

        # Formatação para exibição na tabela
        df_disp = df_filtered.copy()
        for c in ['Orcado', 'Realizado', 'Diferença']:
            df_disp[c] = df_disp[c].apply(lambda x: f"R$ {x:,.2f}")
            
        st.dataframe(df_disp.drop(columns=['Mes_Num']), use_container_width=True)
        
    else:
        st.warning(f"Nenhum dado encontrado para {st.session_state.setor} no ano {ano_sel}.")