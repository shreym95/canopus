from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text
from rich import box

console = Console()


def score_color(score: float) -> str:
    if score >= 8:
        return "bright_green"
    if score >= 6:
        return "yellow"
    return "red"


def show_jobs_table(jobs: list[dict]):
    table = Table(box=box.ROUNDED, show_lines=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("Score", width=6, justify="center")
    table.add_column("Title", min_width=30)
    table.add_column("Company", min_width=20)
    table.add_column("Location", min_width=15)
    table.add_column("Salary", min_width=12)
    table.add_column("Source", width=10)

    for i, job in enumerate(jobs, 1):
        score = job.get("score") or 0
        color = score_color(score)
        table.add_row(
            str(i),
            Text(f"{score:.1f}", style=f"bold {color}"),
            job["title"],
            job["company"],
            job.get("location") or "",
            job.get("salary_text") or "—",
            job["source"],
        )

    console.print(table)


def review_job(job: dict, index: int, total: int) -> str:
    """Show full job detail. Returns: 'approve' | 'skip' | 'blacklist' | 'quit'."""
    console.rule(f"[bold cyan]Job {index}/{total}[/]")
    console.print(Panel(
        f"[bold]{job['title']}[/bold]\n"
        f"[cyan]{job['company']}[/cyan]  ·  {job.get('location', '')}  ·  {job.get('work_mode', '')}\n"
        f"Salary: {job.get('salary_text') or '—'}\n"
        f"Source: [dim]{job['source']}[/dim]  ·  {job['url']}\n\n"
        f"[yellow]Score: {job.get('score', '?')}/10[/yellow] — {job.get('score_reason', '')}",
        title="Job Details",
        border_style="cyan",
    ))

    desc = job.get("description") or ""
    if desc:
        console.print(Panel(
            desc[:1500] + ("..." if len(desc) > 1500 else ""),
            title="Description (excerpt)",
            border_style="dim",
        ))

    console.print(
        "\n[bold green]a[/] approve  "
        "[bold yellow]s[/] skip  "
        "[bold red]b[/] blacklist company  "
        "[bold]q[/] quit review\n"
    )

    while True:
        choice = Prompt.ask("Choice", choices=["a", "s", "b", "q"], default="s")
        return {"a": "approve", "s": "skip", "b": "blacklist", "q": "quit"}[choice]


def run_review(jobs: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Interactive review loop.
    Returns (approved_jobs, blacklisted_companies).
    """
    if not jobs:
        console.print("[yellow]No jobs to review.[/]")
        return [], []

    console.print(f"\n[bold cyan]Found {len(jobs)} ranked jobs for review[/]\n")
    show_jobs_table(jobs)
    console.print("\nPress Enter to start reviewing each job...\n")
    input()

    approved = []
    blacklisted = []

    for i, job in enumerate(jobs, 1):
        action = review_job(job, i, len(jobs))
        if action == "approve":
            approved.append(job)
            console.print(f"[green]✓ Approved: {job['title']} @ {job['company']}[/]")
        elif action == "blacklist":
            blacklisted.append(job["company"])
            console.print(f"[red]✗ Blacklisted: {job['company']}[/]")
        elif action == "quit":
            console.print("[yellow]Review ended early.[/]")
            break
        else:
            console.print(f"[dim]Skipped: {job['title']}[/]")

    console.print(f"\n[bold]Review complete: {len(approved)} approved, {len(blacklisted)} blacklisted[/]")
    return approved, blacklisted
