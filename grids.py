import streamlit as st

def render_aggrid(df, key="grid", height=420, fit_columns=True):
    """
    Renderiza un DataFrame con AgGrid si está disponible.
    Si no, usa st.dataframe como fallback (para no romper deploys).
    """
    try:
        from st_aggrid import AgGrid, GridOptionsBuilder
        gob = GridOptionsBuilder.from_dataframe(df)
        if fit_columns:
            gob.configure_default_column(resizable=True, filter=True, sortable=True)
            gob.configure_grid_options(domLayout="normal")
        grid_options = gob.build()

        return AgGrid(
            df,
            gridOptions=grid_options,
            height=height,
            key=key,
            fit_columns_on_grid_load=fit_columns,
        )
    except Exception:
        st.dataframe(df, use_container_width=True)
        return None
