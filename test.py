import streamlit as st
import pandas as pd
import unicodedata
import re
from pathlib import Path

st.set_page_config(page_title="Chiffrage sinistre", layout="wide")

REPL_MAP = {
    r"\'ea": "ê",
    r"\'e9": "é",
    r"\'e8": "è",
    r"\'b": "",
    r"\'ef": "ï",
    r"\'e7": "ç",
    r"\'e2": "â",
    r"\'9c": "œ",
    r"\'e0": "à",
    r"\'ee": "î",
}

SELECTOR_MAP = {
    "Menuiseries extérieures": "Extérieure",
    "Menuiserie intérieure": "Intérieure",
    "Revêtements de sol": "Sol",
    "Revêtements murs et plafonds": "Murs et plafonds",
    "Charpente - Ossature": "Charpente - Ossature",
    "Maçonnerie - Gros œuvre": "Maçonnerie - Gros œuvre",
    "Plomberie": "Plomberie",
    "Electricité": "Electricité",
    "Chauffage - Ventilation - Climatisation": "Chauffage - Ventilation - Climatisation",
}

CATEGORY_MERGE_MAP = {
    "Revêtements de sol": "Revêtements intérieurs",
    "Revêtements murs et plafonds": "Revêtements intérieurs",
    "Menuiseries extérieures": "Menuiseries",
    "Menuiserie intérieure": "Menuiseries",
    "Charpente - Ossature": "Structure",
    "Maçonnerie - Gros œuvre": "Structure",
    "Plomberie": "Réseaux techniques",
    "Electricité": "Réseaux techniques",
    "Chauffage - Ventilation - Climatisation": "Réseaux techniques",
}

LOW_CARBON_KEYWORDS = [
    "bas carbone",
    "chaume",
    "végétalisée",
    "biosourcé",
    "biosourcée",
    "laine",
    "chanvre",
    "ouate de cellulose",
]


def normalize_text(value: str) -> str:
    if pd.isna(value):
        return ""
    text = str(value).lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text


def normalize_colname(value: str) -> str:
    text = normalize_text(value)
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text


NORMALIZED_LOW_CARBON_KEYWORDS = [normalize_text(x) for x in LOW_CARBON_KEYWORDS]


def is_low_carbon_option(row: pd.Series) -> bool:
    text = f"{row.get('Sous_categorie', '')} {row.get('Produit_process', '')}"
    text_norm = normalize_text(text)
    keyword_match = any(keyword in text_norm for keyword in NORMALIZED_LOW_CARBON_KEYWORDS)
    emissions = row.get("Emissions_CO2")
    emissions_rule = pd.notna(emissions) and float(emissions) <= 0
    return keyword_match or emissions_rule


def find_html_path() -> Path:
    here = Path(__file__).resolve().parent
    candidates = [
        here / "carbon_data.html",
        here.parent / "carbon_data.html",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("carbon_data.html introuvable.")


def find_company_xlsx_path() -> Path:
    here = Path(__file__).resolve().parent
    candidates = [
        here / "full_list_.xlsx",
        here / "full_list.xlsx",
        here.parent / "full_list_.xlsx",
        here.parent / "full_list.xlsx",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("full_list_.xlsx / full_list.xlsx introuvable.")


def resolve_column(df: pd.DataFrame, aliases: list[str], required: bool = True) -> str | None:
    normalized_map = {normalize_colname(col): col for col in df.columns}
    for alias in aliases:
        key = normalize_colname(alias)
        if key in normalized_map:
            return normalized_map[key]
    if required:
        raise KeyError(f"Colonne introuvable parmi: {aliases}")
    return None


@st.cache_data
def load_df(html_path: str) -> pd.DataFrame:
    tables = pd.read_html(html_path)
    if not tables:
        raise ValueError("No tables found in carbon_data.html")

    df = tables[0].copy()

    df.columns = [
        "Categorie",
        "Sous_categorie",
        "Produit_process",
        "Unite",
        "Type_prestation",
        "Prestation",
        "Emissions_CO2",
    ]

    df = df.iloc[1:].reset_index(drop=True)

    for col in df.columns:
        if df[col].dtype == object:
            s = df[col].astype(str)
            for pat, repl in REPL_MAP.items():
                s = s.str.replace(pat, repl, regex=False)
            df[col] = s

    df["Emissions_CO2"] = pd.to_numeric(df["Emissions_CO2"], errors="coerce")

    df["Categorie_old"] = df["Categorie"]
    df["Selector"] = df["Categorie"].map(SELECTOR_MAP)
    df["Categorie"] = df["Categorie"].replace(CATEGORY_MERGE_MAP)

    return df


@st.cache_data
def load_company_df(xlsx_path: str) -> pd.DataFrame:
    raw = pd.read_excel(xlsx_path)

    entreprise_col = resolve_column(raw, ["Entreprise"])
    specificites_col = resolve_column(raw, ["Spécifités", "Specificites"], required=False)
    region_cov_col = resolve_column(raw, ["Région de couverture", "Region de couverture"], required=False)
    region_hq_col = resolve_column(
        raw,
        ["Région du/des siège(s) social(s)", "Region du/des siege(s) social(s)", "Région du/des sièges sociaux"],
        required=False,
    )
    categories_col = resolve_column(raw, ["Catégorie d'outil associée", "Categorie d'outil associee"])
    description_col = resolve_column(raw, ["Description"], required=False)
    savings_col = resolve_column(raw, ["Économies d'émissions", "Economies d'emissions"], required=False)
    link_col = resolve_column(raw, ["Link", "Lien"], required=False)

    companies = pd.DataFrame(
        {
            "Entreprise": raw[entreprise_col].astype(str).fillna(""),
            "Spécifités": raw[specificites_col].astype(str).fillna("") if specificites_col else "",
            "Région de couverture": raw[region_cov_col].astype(str).fillna("") if region_cov_col else "",
            "Région du/des siège(s) social(s)": raw[region_hq_col].astype(str).fillna("") if region_hq_col else "",
            "Description": raw[description_col].astype(str).fillna("") if description_col else "",
            "Économies d'émissions": raw[savings_col].astype(str).fillna("") if savings_col else "",
            "Link": raw[link_col].astype(str).fillna("") if link_col else "",
            "Catégorie d'outil associée": raw[categories_col].astype(str).fillna(""),
        }
    )

    companies["Entreprise"] = companies["Entreprise"].replace("nan", "").str.strip()
    companies["Spécifités"] = companies["Spécifités"].replace("nan", "").str.strip()
    companies["Région de couverture"] = companies["Région de couverture"].replace("nan", "").str.strip()
    companies["Région du/des siège(s) social(s)"] = companies["Région du/des siège(s) social(s)"].replace("nan", "").str.strip()
    companies["Description"] = companies["Description"].replace("nan", "").str.strip()
    companies["Économies d'émissions"] = companies["Économies d'émissions"].replace("nan", "").str.strip()
    companies["Link"] = companies["Link"].replace("nan", "").str.strip()

    companies["Categories_associees_list"] = companies["Catégorie d'outil associée"].apply(
        lambda x: [normalize_text(part) for part in str(x).split(",") if str(part).strip()]
    )

    companies = companies[companies["Entreprise"] != ""].reset_index(drop=True)
    return companies


def build_candidates(filtered_df: pd.DataFrame) -> pd.DataFrame:
    candidates = (
        filtered_df[
            [
                "Categorie",
                "Categorie_old",
                "Selector",
                "Sous_categorie",
                "Produit_process",
                "Unite",
                "Type_prestation",
                "Prestation",
                "Emissions_CO2",
            ]
        ]
        .dropna(subset=["Produit_process", "Emissions_CO2"])
        .drop_duplicates()
        .copy()
    )

    if candidates.empty:
        return candidates

    candidates["Option_famille"] = candidates.apply(
        lambda row: "Option bas carbone" if is_low_carbon_option(row) else "Standard",
        axis=1,
    )

    candidates = candidates.sort_values(
        ["Option_famille", "Emissions_CO2", "Produit_process"],
        ascending=[True, True, True],
    ).reset_index(drop=True)

    return candidates


def make_option_table(option_df: pd.DataFrame) -> pd.DataFrame:
    if option_df.empty:
        return option_df

    table = option_df.copy()
    table["Émissions spécifiques (kg CO₂ / unité)"] = table["Emissions_CO2"].astype(float).round(2)

    table = table[
        [
            "Produit_process",
            "Unite",
            "Émissions spécifiques (kg CO₂ / unité)",
        ]
    ].rename(
        columns={
            "Produit_process": "Produit / process",
            "Unite": "Unité",
        }
    )

    return table.reset_index(drop=True)


def highlight_selected(row: pd.Series, selected_product: str | None):
    if selected_product is not None and row["Produit / process"] == selected_product:
        return ["background-color: #0099FF; font-weight: 600"] * len(row)
    return [""] * len(row)


def filter_companies_by_category(companies: pd.DataFrame, category_value: str) -> pd.DataFrame:
    normalized_category = normalize_text(category_value)
    matched = companies[
        companies["Categories_associees_list"].apply(lambda values: normalized_category in values)
    ].copy()
    return matched.reset_index(drop=True)


html_path = find_html_path()
company_xlsx_path = find_company_xlsx_path()

df = load_df(str(html_path))
company_df = load_company_df(str(company_xlsx_path))

if "basket" not in st.session_state:
    st.session_state.basket = []

st.title("Chiffrage sinistre")

left, right = st.columns([1, 2])

selected_row = None
selected_product = None
selected_family = None
standard_df = pd.DataFrame()
low_carbon_df = pd.DataFrame()

with left:
    st.subheader("Ajouter une ligne")

    categories = sorted(df["Categorie"].dropna().unique().tolist())
    idx_map = {cat: i + 1 for i, cat in enumerate(categories)}

    cat = st.selectbox(
        "Catégorie",
        options=categories,
        format_func=lambda x: f"{idx_map.get(x, '')}. {x}",
        key="cat",
    )
    d1 = df[df["Categorie"] == cat]

    selector_options = sorted(
        [x for x in d1["Selector"].dropna().unique().tolist() if x != ""]
    )
    if len(selector_options) == 0:
        selector = None
        d2 = d1
        st.caption("Sélecteur : non applicable")
    else:
        selector = st.selectbox("Sélecteur", options=selector_options, key="selector")
        d2 = d1[d1["Selector"] == selector]

    sous_cat = st.selectbox(
        "Sous-catégorie",
        options=sorted(d2["Sous_categorie"].dropna().unique().tolist()),
        key="sous_cat",
    )
    d3 = d2[d2["Sous_categorie"] == sous_cat]

    type_prest = st.selectbox(
        "Type de prestation",
        options=sorted(d3["Type_prestation"].dropna().unique().tolist()),
        key="type_prest",
    )
    d4 = d3[d3["Type_prestation"] == type_prest]

    prest = st.selectbox(
        "Prestation",
        options=sorted(d4["Prestation"].dropna().unique().tolist()),
        key="prest",
    )
    d5 = d4[d4["Prestation"] == prest]

    candidates = build_candidates(d5)

    standard_df = candidates[candidates["Option_famille"] == "Standard"].reset_index(drop=True)
    low_carbon_df = candidates[candidates["Option_famille"] == "Option bas carbone"].reset_index(drop=True)

    available_families = []
    if not standard_df.empty:
        available_families.append("Standard")
    if not low_carbon_df.empty:
        available_families.append("Option bas carbone")

    if not available_families:
        st.warning("Aucun produit/process correspondant à cette combinaison.")
    else:
        default_family = "Option bas carbone" if "Option bas carbone" in available_families else available_families[0]

        selected_family = st.radio(
            "Choix du type d'option",
            options=available_families,
            index=available_families.index(default_family),
            horizontal=True,
            key="option_family",
        )

        active_df = low_carbon_df if selected_family == "Option bas carbone" else standard_df
        option_ids = list(active_df.index)

        selected_option_id = st.selectbox(
            "Produit / process",
            options=option_ids,
            format_func=lambda i: (
                f"{active_df.loc[i, 'Produit_process']} — "
                f"{float(active_df.loc[i, 'Emissions_CO2']):.2f} kg CO₂ / "
                f"{active_df.loc[i, 'Unite']}"
            ),
            key="product_option",
        )

        selected_row = active_df.loc[selected_option_id]
        selected_product = str(selected_row["Produit_process"])
        unit = str(selected_row["Unite"]) if pd.notna(selected_row["Unite"]) else ""

        qty = st.number_input(
            f"Quantité de matière ({unit})",
            min_value=0.0,
            value=1.0,
            step=1.0,
            key="qty",
        )

        emissions_per_unit = float(selected_row["Emissions_CO2"])
        emissions_total = emissions_per_unit * float(qty)

        c1, c2 = st.columns(2)
        c1.metric(f"kg CO₂ / {unit}", f"{emissions_per_unit:.2f}")
        c2.metric("kg CO₂ total", f"{emissions_total:.2f}")

        add = st.button("Ajouter au chiffrage", type="primary", use_container_width=True)

        if add:
            st.session_state.basket.append(
                {
                    "Categorie": str(selected_row["Categorie"]),
                    "Categorie_old": str(selected_row["Categorie_old"]),
                    "Selector": "" if selector is None else str(selector),
                    "Sous_categorie": str(selected_row["Sous_categorie"]),
                    "Type_prestation": str(selected_row["Type_prestation"]),
                    "Prestation": str(selected_row["Prestation"]),
                    "Option_famille": str(selected_family),
                    "Produit_process": str(selected_row["Produit_process"]),
                    "Unite": unit,
                    "Quantite": float(qty),
                    "Emissions_specifiques": float(emissions_per_unit),
                    "kg_CO2_total": float(emissions_total),
                }
            )
            st.success("Ligne ajoutée.")
            st.rerun()

with right:
    options_tab, companies_tab = st.tabs(["Options Produit / process", "Entreprises associées"])

    with options_tab:
        st.subheader("Options Produit / process")

        st.markdown("#### Option bas carbone")
        if low_carbon_df.empty:
            st.info("Aucune option bas carbone.")
        else:
            low_table = make_option_table(low_carbon_df)
            low_styled = low_table.style.apply(
                lambda row: highlight_selected(
                    row,
                    selected_product if selected_family == "Option bas carbone" else None,
                ),
                axis=1,
            )
            st.dataframe(low_styled, use_container_width=True, hide_index=True)

        st.markdown("#### Standard")
        if standard_df.empty:
            st.info("Aucune option standard.")
        else:
            standard_table = make_option_table(standard_df)
            standard_styled = standard_table.style.apply(
                lambda row: highlight_selected(
                    row,
                    selected_product if selected_family == "Standard" else None,
                ),
                axis=1,
            )
            st.dataframe(standard_styled, use_container_width=True, hide_index=True)

        if selected_row is not None:
            with st.expander("Debug : ligne correspondante (Avensys)"):
                debug_df = pd.DataFrame([selected_row]).copy()
                if "Categorie_old" in debug_df.columns:
                    debug_df["Categorie"] = debug_df["Categorie_old"]
                debug_df = debug_df.drop(columns=["Categorie_old"], errors="ignore")
                st.dataframe(debug_df, use_container_width=True, hide_index=True)

    with companies_tab:
        st.subheader(f"Entreprises liées à la catégorie : {cat}")

        matched_companies = filter_companies_by_category(company_df, cat)

        if matched_companies.empty:
            st.info("Aucune entreprise associée à cette catégorie.")
        else:
            company_summary = matched_companies[
                [
                    "Entreprise",
                    "Spécifités",
                    "Région de couverture",
                    "Région du/des siège(s) social(s)",
                ]
            ].reset_index(drop=True)

            st.caption("Cliquez sur une ligne pour afficher le détail de l’entreprise.")
            company_selection = st.dataframe(
                company_summary,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
            )

            selected_company_idx = None
            if company_selection.selection.rows:
                selected_company_idx = company_selection.selection.rows[0]

            if selected_company_idx is not None:
                selected_company = matched_companies.iloc[selected_company_idx]

                st.markdown("#### Détail de l’entreprise")
                company_detail = pd.DataFrame(
                    [
                        {
                            "Description": selected_company["Description"],
                            "Économies d'émissions": selected_company["Économies d'émissions"],
                            "Link": selected_company["Link"],
                        }
                    ]
                )

                st.dataframe(
                    company_detail,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Link": st.column_config.LinkColumn("Link"),
                    },
                )
            else:
                st.info("Sélectionnez une entreprise dans le tableau ci-dessus.")

st.markdown("---")
st.subheader("Chiffrage (lignes)")

if st.session_state.basket:
    basket_df = pd.DataFrame(st.session_state.basket)
    basket_display = basket_df.copy()

    basket_display["Quantite"] = basket_display["Quantite"].round(2)
    basket_display["Emissions_specifiques"] = basket_display["Emissions_specifiques"].round(2)
    basket_display["kg_CO2_total"] = basket_display["kg_CO2_total"].round(2)

    basket_display = basket_display.rename(
        columns={
            "Selector": "Sélecteur",
            "Sous_categorie": "Sous-catégorie",
            "Type_prestation": "Type de prestation",
            "Option_famille": "Famille d'option",
            "Produit_process": "Produit / process",
            "Unite": "Unité",
            "Quantite": "Quantité",
            "Emissions_specifiques": "Émissions spécifiques (kg CO₂ / unité)",
            "kg_CO2_total": "kg CO₂ total",
        }
    )

    display_cols = [
        "Categorie",
        "Sélecteur",
        "Sous-catégorie",
        "Type de prestation",
        "Prestation",
        "Famille d'option",
        "Produit / process",
        "Unité",
        "Quantité",
        "Émissions spécifiques (kg CO₂ / unité)",
        "kg CO₂ total",
    ]

    st.dataframe(basket_display[display_cols], use_container_width=True, hide_index=True)

    total = float(basket_df["kg_CO2_total"].sum())
    st.metric("Total chiffrage (kg CO₂)", f"{total:.2f}")

    st.subheader("Répartition du CO₂ par catégorie")

    by_cat = (
        basket_df.groupby("Categorie", as_index=False)["kg_CO2_total"]
        .sum()
        .sort_values("kg_CO2_total", ascending=False)
    )

    st.bar_chart(by_cat.set_index("Categorie")["kg_CO2_total"])

    by_cat_display = by_cat.copy()
    by_cat_display["kg_CO2_total"] = by_cat_display["kg_CO2_total"].round(2)
    by_cat_display = by_cat_display.rename(columns={"kg_CO2_total": "kg CO₂ total"})
    st.dataframe(by_cat_display, use_container_width=True, hide_index=True)

    st.subheader("Actions")
    c1, c2 = st.columns(2)

    with c1:
        if st.button("Retirer la dernière ligne", use_container_width=True):
            st.session_state.basket.pop()
            st.rerun()

    with c2:
        st.download_button(
            "Télécharger CSV",
            data=basket_df.to_csv(index=False).encode("utf-8"),
            file_name="chiffrage_sinistre.csv",
            mime="text/csv",
            use_container_width=True,
        )

    c3, c4 = st.columns(2)
    with c3:
        if st.button("Vider le chiffrage", use_container_width=True):
            st.session_state.basket = []
            st.rerun()
    with c4:
        st.metric("CO₂ cumulé", f"{total:.2f} kg")

else:
    st.info("Aucune ligne ajoutée pour l’instant.")