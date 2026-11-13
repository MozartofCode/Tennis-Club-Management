"""Print how well the models do on the current database.

    uv run python -m scripts.train

Demand: mean absolute error on the last two weeks, held out.
Churn: AUC, precision and recall on the most recent snapshot, held out (time split).
Pricing: the flat vs dynamic simulation over the last 8 weeks, default assumptions.
"""

from sqlalchemy import select

from app.ai import churn, demand
from app.api.pricing import simulate
from app.db import SessionLocal
from app.models import Club, User
from app.timeutil import club_now


def main() -> None:
    with SessionLocal() as db:
        for club in db.scalars(select(Club)).all():
            print(f"\n== {club.name} ==")
            dm = demand.train(db, club, club_now(club.timezone).date())
            mae = f"{dm.mae:.3f}" if dm.mae is not None else "n/a"
            print(f"Demand model: {'gradient boosting' if dm.model else 'recent averages'}")
            print(f"  training court-hours: {dm.rows}")
            print(f"  holdout MAE (share of courts booked): {mae}")

            result = churn.score_club(db, club)
            print(f"Churn model: {result['model']}")
            for k in ("training_rows", "test_rows", "test_churn_rate", "auc"):
                if k in result:
                    print(f"  {k}: {result[k]}")
            if "precision_high" in result:
                print(
                    f"  high band on holdout: precision {result['precision_high']}, "
                    f"recall {result['recall_high']} ({result['flagged_high']} flagged)"
                )
            print(
                f"  current members: {result.get('high', 0)} high, {result.get('medium', 0)} medium"
            )

            staff = db.scalar(
                select(User).where(User.club_id == club.id, User.role.in_(("owner", "staff")))
            )
            if staff:
                sim = simulate(weeks=8, elasticity=0.6, unmet=0.15, _=staff, club=club, db=db)
                lift = (sim.dynamic_revenue - sim.flat_revenue) / max(sim.flat_revenue, 1)
                print(
                    "Pricing simulation (8 weeks, elasticity 0.6, 15% unmet demand at full hours):"
                )
                flat, dyn = sim.flat_revenue, sim.dynamic_revenue
                print(f"  revenue: ${flat:,.0f} flat -> ${dyn:,.0f} ({lift:+.1%})")
                pk_flat, pk_dyn = sim.peak_util_flat, sim.peak_util_dynamic
                print(f"  peak utilization: {pk_flat:.0%} -> {pk_dyn:.0%}")
                print(
                    f"  off-peak utilization: {sim.offpeak_util_flat:.0%} -> "
                    f"{sim.offpeak_util_dynamic:.0%}"
                )


if __name__ == "__main__":
    main()
