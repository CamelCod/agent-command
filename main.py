"""
main.py — Entry point for Agent Command.

Run this to talk to your AI agent team.
You speak to NEXUS. The team builds.

Usage:
  python main.py "Build me a ..."
  python main.py --evolve           (force evolve all agents)
  python main.py --health           (show team fitness dashboard)
  python main.py --history FORGE    (show FORGE's evolution history)
  python main.py --interactive      (REPL mode)
"""

from __future__ import annotations
import asyncio
import sys
import argparse
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from heart.memoria import Memoria
from heart.echo import Echo
from heart.darwin import Darwin
from heart.analytics import PipelineAnalytics
from graph import build_graph, create_initial_state
import config

console = Console()


# ─────────────────────────────────────────────────────────────────────────────
#  System Boot
# ─────────────────────────────────────────────────────────────────────────────

async def boot() -> tuple[Memoria, Echo, Darwin, PipelineAnalytics]:
    """Initialize all heart systems."""
    console.print("\n[bold amber]AGENT COMMAND[/bold amber] [dim]— Booting...[/dim]")

    memoria = Memoria(config.DB_PATH)
    await memoria.initialize()
    console.print("  [green]✓[/green] MEMORIA online")

    echo = Echo(memoria)
    console.print("  [green]✓[/green] ECHO online")

    darwin = Darwin(memoria)
    console.print("  [green]✓[/green] DARWIN online")

    analytics = PipelineAnalytics(memoria)
    console.print("  [green]✓[/green] ANALYTICS online")

    return memoria, echo, darwin, analytics


# ─────────────────────────────────────────────────────────────────────────────
#  Core Build Runner
# ─────────────────────────────────────────────────────────────────────────────

async def run_build(human_intent: str, needs_ai: bool = False):
    """Execute a full build from a human intent string."""
    memoria, echo, darwin, analytics = await boot()
    graph = build_graph(memoria, echo, darwin, analytics)

    console.print(Panel(
        f"[bold]{human_intent}[/bold]",
        title="[amber]Your Intent[/amber]",
        border_style="dim"
    ))

    # Auto-detect AI feature need from keywords
    ai_keywords = ["ai", "llm", "rag", "embedding", "chat", "assistant", "gpt", "claude"]
    if any(kw in human_intent.lower() for kw in ai_keywords):
        needs_ai = True
        console.print("[dim]  → AI features detected — WEAVE will be activated[/dim]")

    initial_state = create_initial_state(human_intent, needs_ai)

    console.print("\n[bold green]▶ Pipeline starting...[/bold green]\n")

    try:
        final_state = await graph.ainvoke(initial_state)
        console.print("\n[bold green]✓ Build complete.[/bold green]")
        return final_state
    except Exception as e:
        console.print(f"\n[bold red]✗ Pipeline error: {e}[/bold red]")
        raise


# ─────────────────────────────────────────────────────────────────────────────
#  Dashboard Commands
# ─────────────────────────────────────────────────────────────────────────────

async def show_health():
    """Display team fitness dashboard."""
    memoria, _, _, _ = await boot()
    health = await memoria.get_team_health()

    table = Table(title="Agent Team Health Dashboard", border_style="dim")
    table.add_column("Agent",    style="bold", width=10)
    table.add_column("Tier",     style="dim",  width=5)
    table.add_column("Fitness",  width=18)
    table.add_column("Runs",     justify="right", width=6)
    table.add_column("Genome",   width=10)
    table.add_column("Model",    style="dim", width=25)

    for agent_id, data in sorted(health.items(), key=lambda x: x[1]["fitness"], reverse=True):
        tier = config.AGENT_TIERS.get(agent_id, "??")
        fitness = data["fitness"]
        bar_filled = "█" * int(fitness)
        bar_empty  = "░" * (10 - int(fitness))
        color = "green" if fitness >= 7.5 else "yellow" if fitness >= 5.0 else "red"

        table.add_row(
            agent_id,
            tier,
            f"[{color}]{bar_filled}{bar_empty}[/{color}] {fitness:.1f}",
            str(data["runs"]),
            f"v{data['genome_version']} gen{data['generation']}",
            data["model"],
        )

    console.print(table)


async def show_history(agent_id: str):
    """Show the evolution history for a specific agent."""
    memoria, _, _, _ = await boot()
    history = await memoria.get_evolution_history(agent_id)

    if not history:
        console.print(f"[dim]No evolution history for {agent_id}[/dim]")
        return

    table = Table(title=f"{agent_id} Evolution History", border_style="dim")
    table.add_column("Version",  width=12)
    table.add_column("Trigger",  width=20)
    table.add_column("Weak Dims", width=30)
    table.add_column("Fitness",  width=10)
    table.add_column("Accepted", width=10)
    table.add_column("Timestamp", width=25)

    for r in history:
        accepted_str = "[green]✓ YES[/green]" if r["accepted"] else "[red]✗ NO[/red]"
        table.add_row(
            f"v{r['from_version']} → v{r['to_version']}",
            r["trigger"][:18],
            ", ".join(r["weak_dimensions"]),
            f"{r['fitness_before']:.2f}",
            accepted_str,
            r["timestamp"][:19],
        )

    console.print(table)


async def force_evolve():
    """Force evolution of all agents."""
    memoria, _, darwin, _ = await boot()
    console.print("[bold yellow]⚡ Force evolving all agents...[/bold yellow]")
    records = await darwin.evolve_team()
    console.print(f"[green]✓ Evolved {len(records)} agent(s)[/green]")
    for r in records:
        console.print(f"  {r['agent_id']}: v{r['from_version']} → v{r['to_version']}")


# ─────────────────────────────────────────────────────────────────────────────
#  Interactive REPL
# ─────────────────────────────────────────────────────────────────────────────

async def interactive_mode():
    """Interactive REPL — keep building without restarting."""
    memoria, echo, darwin, analytics = await boot()
    graph = build_graph(memoria, echo, darwin, analytics)

    console.print(Panel(
        "[bold]AGENT COMMAND — Interactive Mode[/bold]\n"
        "[dim]Type your intent. The team builds.\n"
        "Commands: /health  /evolve  /history <AGENT>  /quit[/dim]",
        border_style="amber"
    ))

    while True:
        try:
            intent = console.input("\n[bold amber]YOU →[/bold amber] ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not intent:
            continue

        if intent == "/quit":
            break
        elif intent == "/health":
            await show_health()
            continue
        elif intent == "/evolve":
            records = await darwin.evolve_team()
            console.print(f"[green]Evolved {len(records)} agent(s)[/green]")
            continue
        elif intent.startswith("/history "):
            agent_id = intent.split(" ", 1)[1].upper()
            await show_history(agent_id)
            continue

        # Detect AI features
        ai_keywords = ["ai", "llm", "rag", "embedding", "chat", "assistant"]
        needs_ai = any(kw in intent.lower() for kw in ai_keywords)

        initial_state = create_initial_state(intent, needs_ai)

        try:
            await graph.ainvoke(initial_state)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Agent Command — AI Software Builder Team",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py "Build a SaaS for UAE construction tenders with Arabic support"
  python main.py "Add an AI document Q&A feature to Bannaa"
  python main.py --health
  python main.py --evolve
  python main.py --history FORGE
  python main.py --interactive
        """
    )
    parser.add_argument("intent", nargs="?", help="What to build")
    parser.add_argument("--ai",          action="store_true", help="Force activate WEAVE")
    parser.add_argument("--health",      action="store_true", help="Show team health dashboard")
    parser.add_argument("--evolve",      action="store_true", help="Force evolve all agents")
    parser.add_argument("--history",     metavar="AGENT",     help="Show agent evolution history")
    parser.add_argument("--interactive", action="store_true", help="REPL mode")

    args = parser.parse_args()

    if not config.KIMI_API_KEY:
        console.print("[red]Error: KIMI_API_KEY not set. Add it to .env[/red]")
        sys.exit(1)

    if args.health:
        asyncio.run(show_health())
    elif args.evolve:
        asyncio.run(force_evolve())
    elif args.history:
        asyncio.run(show_history(args.history.upper()))
    elif args.interactive:
        asyncio.run(interactive_mode())
    elif args.intent:
        asyncio.run(run_build(args.intent, needs_ai=args.ai))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
