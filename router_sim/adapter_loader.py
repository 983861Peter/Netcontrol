import importlib

def get_vendor_adapter(model: str):
    """
    Dynamically loads a router adapter based on the model or vendor name.
    """
    if not model:
        return None
    model_lower = model.lower()

    # Map models to module names
    # Assuming adapters are in the same package or a subpackage
    if "dlink" in model_lower or "d-link" in model_lower:
        module_name = "router_sim.dlink_adapter"
    elif "ruijie" in model_lower:
        module_name = "router_sim.adapters.ruijie_adapter"
    else:
        module_name = "router_sim.dlink_adapter" # Fallback default

    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None