from types import SimpleNamespace

from groundmeas.ui import dashboard


class DummyContext:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class DummyStreamlit:
    def __init__(self, button_sequence=None):
        self.session_state = {}
        self._button_iter = iter(button_sequence or [])
        self.sidebar = SimpleNamespace(
            header=self._noop,
            multiselect=self._sidebar_multiselect,
            write=self._noop,
        )

    def _noop(self, *args, **kwargs):
        return None

    def _sidebar_multiselect(self, label, options, default=None, **kwargs):
        return default if default is not None else []

    def cache_data(self, func=None):
        if func is None:
            return lambda f: f
        return func

    def set_page_config(self, *args, **kwargs):
        return None

    def title(self, *args, **kwargs):
        return None

    def write(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None

    def divider(self, *args, **kwargs):
        return None

    def header(self, *args, **kwargs):
        return None

    def subheader(self, *args, **kwargs):
        return None

    def json(self, *args, **kwargs):
        return None

    def dataframe(self, *args, **kwargs):
        return None

    def plotly_chart(self, *args, **kwargs):
        return None

    def checkbox(self, *args, value=False, **kwargs):
        return value

    def number_input(self, *args, value=0.0, **kwargs):
        return value

    def selectbox(self, label, options, index=0, **kwargs):
        return options[index]

    def text_input(self, *args, value="", **kwargs):
        return value

    def multiselect(self, label, options, key=None, **kwargs):
        if key and key in self.session_state:
            return self.session_state[key]
        return []

    def tabs(self, labels):
        return [DummyContext() for _ in labels]

    def expander(self, *args, **kwargs):
        return DummyContext()

    def button(self, *args, **kwargs):
        try:
            return next(self._button_iter)
        except StopIteration:
            return False

    def rerun(self):
        return None


def test_resolve_db_path_env(monkeypatch):
    monkeypatch.setenv("GROUNDMEAS_DB", "env.db")
    assert dashboard.resolve_db_path() == "env.db"


def test_parse_float_list():
    assert dashboard._parse_float_list("1, 2; 3") == [1.0, 2.0, 3.0]


def test_main_runs_with_stubs(monkeypatch):
    dummy = DummyStreamlit(button_sequence=[True, True, True, True, True, True])
    dummy.session_state["multiselect_ids"] = [1]
    monkeypatch.setattr(dashboard, "st", dummy)
    monkeypatch.setattr(
        dashboard,
        "st_folium",
        lambda *args, **kwargs: {"last_object_clicked_tooltip": None},
    )
    monkeypatch.setattr(
        dashboard,
        "read_measurements_by",
        lambda **kwargs: (
            [
                {
                    "id": 1,
                    "asset_type": "substation",
                    "location": {"name": "Site", "latitude": 1.0, "longitude": 2.0},
                    "items": [],
                }
            ],
            None,
        ),
    )
    monkeypatch.setattr(dashboard, "plot_imp_over_f_plotly", lambda ids: "fig")
    monkeypatch.setattr(dashboard, "plot_rho_f_model_plotly", lambda ids, coeffs: "fig")
    monkeypatch.setattr(dashboard, "plot_voltage_vt_epr_plotly", lambda ids, frequency=50.0: "fig")
    monkeypatch.setattr(
        dashboard,
        "value_over_distance_detailed",
        lambda ids, measurement_type="earthing_impedance": {1: [{"frequency": 50.0}]},
    )
    monkeypatch.setattr(dashboard, "plot_value_over_distance_plotly", lambda *args, **kwargs: "fig")
    monkeypatch.setattr(
        dashboard,
        "soil_resistivity_curve",
        lambda **kwargs: [{"spacing_m": 1.0, "rho_ohm_m": 10.0}],
    )
    monkeypatch.setattr(dashboard, "multilayer_soil_model", lambda **kwargs: {"layers": []})
    monkeypatch.setattr(dashboard, "plot_soil_model_plotly", lambda **kwargs: "fig")
    monkeypatch.setattr(dashboard, "layered_earth_forward", lambda **kwargs: [1.0])
    monkeypatch.setattr(
        dashboard,
        "invert_soil_resistivity_layers",
        lambda **kwargs: {"layers": [], "misfit": {}, "observed_curve": [], "predicted_curve": []},
    )
    monkeypatch.setattr(dashboard, "plot_soil_inversion_plotly", lambda **kwargs: "fig")

    import groundmeas.analytics as analytics

    monkeypatch.setattr(analytics, "rho_f_model", lambda ids: (1.0, 2.0, 3.0, 4.0, 5.0))

    dashboard.main()
