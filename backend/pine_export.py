from typing import Any, Dict, Optional


def build_pine_script(ticker: str, trade_plan: Dict[str, Any], patterns: Optional[Dict[str, Any]] = None) -> str:
    entry = trade_plan.get("entry_zone", {})
    targets = trade_plan.get("targets", [])
    fib = (patterns or {}).get("fibonacci") or {}
    lines = [
        "//@version=6",
        f'indicator("AlphaDesk Research - {ticker.upper()}", overlay=true)',
        "// Research annotation only. Verify independently; not an execution strategy.",
        _input("Entry low", entry.get("low")), _input("Entry high", entry.get("high")),
        _input("Confirmation", trade_plan.get("confirmation_price")),
        _input("Stop", trade_plan.get("stop_loss")),
        _input("Target 1", targets[0] if targets else None), _input("Target 2", targets[1] if len(targets) > 1 else None),
        'plot(entrylow, "Entry low", color=color.new(color.green, 45), style=plot.style_linebr)',
        'plot(entryhigh, "Entry high", color=color.new(color.green, 45), style=plot.style_linebr)',
        'plot(confirmation, "Confirmation", color=color.blue, style=plot.style_linebr)',
        'plot(stop, "Stop", color=color.red, linewidth=2, style=plot.style_linebr)',
        'plot(target1, "Target 1", color=color.orange, style=plot.style_linebr)',
        'plot(target2, "Target 2", color=color.orange, style=plot.style_linebr)',
    ]
    for ratio, price in fib.get("levels", {}).items():
        variable = "fib" + ratio.replace(".", "")
        lines.extend([f"{variable} = input.price({float(price)}, \"Fib {ratio}\")", f'plot({variable}, "Fib {ratio}", color=color.new(color.purple, 55), style=plot.style_linebr)'])
    return "\n".join(line for line in lines if line)


def _input(label: str, value: Any) -> str:
    number = float(value) if isinstance(value, (int, float)) else 0.0
    variable = label.lower().replace(" ", "")
    return f'{variable} = input.price({number}, "{label}")'
