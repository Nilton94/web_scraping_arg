import streamlit as st 
from utils.utils_scraper import ScraperArgenProp, ScraperZonaProp
from utils.utils_streamlit import get_widgets, get_dataframe, get_map, get_email_widgets, send_mail
import pygwalker as pyg
import streamlit.components.v1 as components
from streamlit_folium import st_folium, folium_static
import re, datetime, pytz

# CONFIGURACOES STREAMLIT
st.set_page_config(
    page_title = "Dados de Imóveis",
    page_icon = 'house',
    layout = 'wide',
    menu_items = {
        'about': 'App para consultar dados de imóveis das bases do Zonaprop e Argenprop. Criado por josenilton1878@gmail.com'
    }

)

# WIDGETS
get_widgets()

if "lista_ids" not in st.session_state:
    st.session_state.lista_ids = []

if 'map' not in st.session_state:
    st.session_state.map = None

try:
    # DADOS
    inicio = datetime.datetime.now(tz = pytz.timezone('America/Sao_Paulo')).replace(microsecond = 0, tzinfo = None)

    df_final = get_dataframe()

    fim = datetime.datetime.now(tz = pytz.timezone('America/Sao_Paulo')).replace(microsecond = 0, tzinfo = None)

    if 'lista_inicio' not in st.session_state:
        st.session_state['lista_inicio'] = []
    if 'lista_fim' not in st.session_state:
        st.session_state['lista_fim'] = []
    if 'lista_duracao' not in st.session_state:
        st.session_state['lista_duracao'] = []

    duracao = fim - inicio

    if duracao > datetime.timedelta(seconds = 30):
        st.session_state['lista_inicio'].insert(0, inicio) 
        st.session_state['lista_fim'].insert(0, fim) 
        st.session_state['lista_duracao'].insert(0, duracao)
    else:
        pass

    st.sidebar.markdown('---')
    try:
        st.sidebar.write(f"<b>Início</b>: {st.session_state['lista_inicio'][0]}", unsafe_allow_html = True)
        st.sidebar.write(f"<b>Fim</b>: {st.session_state['lista_fim'][0]}", unsafe_allow_html = True)
        st.sidebar.write(f"<b>Duração</b>: {st.session_state['lista_fim'][0] - st.session_state['lista_inicio'][0]}", unsafe_allow_html = True)
    except:
        pass

    with st.expander('### Mapa'):
        col1, col2 = st.columns([0.85, 0.15])
        with col1:
            st_data = st_folium(
                get_map(df_final),
                use_container_width = True,
                height = 480
            )
        with col2:
            st.markdown('### Resumo')
            try:
                st.metric(label = 'Imóveis', value = df_final.id.nunique())
            except:
                st.metric(label = 'Imóveis', value = '-')
            try:
                st.metric(label = 'Média Aluguel ($)', value = df_final.loc[df_final['aluguel_moeda'] == '$', 'aluguel_valor'].mean().round(1))
            except:
                st.metric(label = 'Média Aluguel ($)', value = '-')
            try:
                st.metric(label = 'Média Expensas ($)', value = df_final.loc[df_final['expensas_moeda'] == '$', 'expensas_valor'].mean().round(1))
            except:
                st.metric(label = 'Média Expensas ($)', value = '-')
            try:
                st.metric(label = 'Média Ambientes', value = df_final.loc[df_final.ambientes > 0.0, 'ambientes'].mean().round(1))
            except:
                st.metric(label = 'Média Ambientes', value = '-')
            try:
                st.metric(label = 'Média Dormitórios', value = df_final.loc[df_final.dormitorios != 0.0, 'dormitorios'].mean().round(1))
            except:
                st.metric(label = 'Média Dormitórios', value = '-')

        st.session_state.map = st_data

        try:
            if re.search(r'Id: (\d+)', st_data['last_object_clicked_popup']).group(1) not in st.session_state.lista_ids:
                st.session_state.lista_ids.append(
                    str(re.search(r'Id: (\d+)', st_data['last_object_clicked_popup']).group(1))
                )
        except:
            st.write('')
            
    with st.expander('### Base'):
       
        df_pyg = (
            df_final
            .reset_index(drop = True)
            [
                [
                    'id', 'base','tipo_imovel','estado','cidade','bairro', 'endereco', 'url','descricao', 'titulo', 'aluguel_moeda', 'aluguel_valor', 'expensas_moeda', 'expensas_valor', 'valor_total_aluguel',
                    'area_util','ambientes', 'dormitorios', 'banheiros', 'garagens', 'imobiliaria','distancia_hospital_baigorria','distancia_hospital_carrasco','distancia_hospital_ninos','distancia_hospital_provincial',
                    'distancia_unr','latitude','longitude','coordenadas','data','ano','mes','dia'
                ]
            ]
        )
        pyg_html = pyg.walk(
            df_pyg, 
            hideDataSourceConfig = False, 
            themeKey = 'vega', 
            return_html = True
        )

        components.html(
            pyg_html, 
            height = 600, 
            scrolling = True
        )

    with st.expander('### Lista de Imóveis Selecionados'):
        
        get_email_widgets()

        if st.session_state.limpar:
            st.session_state.lista_ids = []

        try:
            st.dataframe(
                (
                    df_final
                    .loc[df_final.id.isin(st.session_state.lista_ids)]
                    .reset_index(drop = True)
                    [[
                        'id', 'base','tipo_imovel','estado','cidade','bairro', 'endereco', 'url', 'aluguel_moeda', 'aluguel_valor', 'expensas_moeda', 'expensas_valor', 'valor_total_aluguel',
                        'area_util','ambientes', 'dormitorios', 'banheiros', 'garagens', 'imobiliaria','distancia_hospital_baigorria','distancia_hospital_carrasco','distancia_hospital_ninos','distancia_hospital_provincial',
                        'distancia_unr','latitude','longitude','coordenadas','data'
                    ]]
                )
            )
        except:
            st.write('Selecione ao menos um imóvel!')

        if st.session_state.enviar_email:
            try:
                df_lista = (
                    df_final
                    .loc[df_final.id.isin(st.session_state.lista_ids)]
                    .reset_index(drop = True)
                    [[
                        'id', 'base','tipo_imovel','estado','cidade','bairro', 'endereco', 'url', 'aluguel_moeda', 'aluguel_valor', 'expensas_moeda', 'expensas_valor', 'valor_total_aluguel',
                        'area_util','ambientes', 'dormitorios', 'banheiros', 'garagens', 'imobiliaria','distancia_hospital_baigorria','distancia_hospital_carrasco','distancia_hospital_ninos','distancia_hospital_provincial',
                        'distancia_unr','latitude','longitude','coordenadas','data'
                    ]]
                )
                send_mail(df = df_lista, emails = st.session_state.email_usuario)
                st.write('E-mail enviado com sucesso!')
            except Exception as e:
                st.error(f'Erro no envio do e-mail: {e}')

except Exception as e:
    # st.write('Selecione ao menos um valor nos filtros de Base, Local e Tipo de Imóvel!')
    st.write('---')
    # st.write(e)