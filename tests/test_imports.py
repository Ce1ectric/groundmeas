def test_import_dashboard_module():
    # Ensure dashboard imports resolve with absolute imports
    import importlib

    mod = importlib.import_module("groundmeas.ui.dashboard")
    assert hasattr(mod, "main")
