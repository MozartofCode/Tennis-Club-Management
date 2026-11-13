"""Generate a realistic demo club with six months of history.

    uv run python -m scripts.seed            # reset the local database and seed it

Members follow personas (regulars, weekend players, daytime players, lesson
takers, new joiners, members who are fading away, and members who already
left). Fading members slow down weeks before their membership lapses, which is
the signal the churn model learns. Peak hours are oversubscribed, which is
what dynamic pricing and the waitlist work with.

Everything is deterministic (fixed random seed) so screenshots are repeatable.
All demo accounts use the password `courtiq-demo`.
"""

import argparse
import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, engine
from app.models import (
    Booking,
    BookingPlayer,
    CheckIn,
    Club,
    Coach,
    Court,
    Match,
    Membership,
    MembershipPlan,
    Notification,
    User,
    WaitlistEntry,
)
from app.security import hash_password, new_qr_token
from app.timeutil import club_now

DEMO_PASSWORD = "courtiq-demo"
HISTORY_DAYS = 182
FUTURE_DAYS = 14
TIMEZONE = "America/New_York"

FIRST = (
    "Ava Ben Chloe Daniel Elena Felix Grace Hugo Isla Jack Kira Leo Maya Noah Olivia Pablo "
    "Quinn Rosa Sam Tara Umar Vera Will Xenia Yusuf Zoe Aisha Bruno Carmen Dev Emre Fatima "
    "Gabe Hana Ivan Jade Kai Lena Marco Nina Omar Priya Raf Sofia Theo Uma Victor Wren Yara "
    "Alex Bea Cyrus Dana Eli Frida Gus Hector Ines Jonah Lucia Mateo Nadia Oscar Paula Ravi"
).split()
LAST = (
    "Adams Baker Chen Diaz Evans Fischer Garcia Hughes Ito Jensen Kaya Lopez Moreau Nakamura "
    "Okafor Patel Quintero Rossi Silva Tanaka Usman Varga Walsh Yilmaz Zhang Novak Berg Costa "
    "Dubois Murphy Kowalski Haddad Sato Larsen Ortiz Price Reyes Stone Torres Weber"
).split()

STYLES = ["baseline", "all-court", "serve-volley", "social"]
GOALS = [
    "Get more consistent on my backhand",
    "Play a league this season",
    "Fitness and fun with friends",
    "Improve my serve",
    "Move up to the next level",
    "Learn to play doubles properly",
    None,
    None,
]


@dataclass
class Persona:
    name: str
    share: float
    per_week: float
    # (weekdays, hours, weight)
    slots: list[tuple[tuple[int, ...], tuple[int, ...], float]]
    lesson_rate: float = 0.05
    plan_weights: tuple[float, float, float, float] = (0.15, 0.35, 0.3, 0.2)  # none,basic,plus,prem


WEEKDAYS = (0, 1, 2, 3, 4)
WEEKEND = (5, 6)
EVENING = (17, 18, 19, 20)
WEEKEND_AM = (8, 9, 10, 11)

PERSONAS = [
    Persona(
        "regular",
        0.28,
        2.4,
        [(WEEKDAYS, EVENING, 0.6), (WEEKEND, WEEKEND_AM, 0.3), (WEEKEND, (14, 15, 16, 17), 0.1)],
    ),
    Persona("weekend", 0.17, 1.3, [(WEEKEND, (8, 9, 10, 11, 12, 13, 14, 15, 16), 1.0)]),
    Persona(
        "daytime",
        0.09,
        2.0,
        [(WEEKDAYS, (8, 9, 10, 11, 13, 14), 0.85), (WEEKEND, (12, 13, 14), 0.15)],
        plan_weights=(0.2, 0.4, 0.3, 0.1),
    ),
    Persona(
        "lessons",
        0.10,
        1.5,
        [(WEEKDAYS, (15, 16, 17, 18), 0.6), (WEEKEND, (9, 10, 11, 12), 0.4)],
        lesson_rate=0.55,
        plan_weights=(0.1, 0.3, 0.35, 0.25),
    ),
    Persona("fading", 0.14, 2.2, [(WEEKDAYS, EVENING, 0.6), (WEEKEND, WEEKEND_AM, 0.4)]),
    Persona("new", 0.09, 1.8, [(WEEKDAYS, (17, 18, 19, 20, 21), 0.6), (WEEKEND, WEEKEND_AM, 0.4)]),
    Persona("churned", 0.06, 2.0, [(WEEKDAYS, EVENING, 0.6), (WEEKEND, WEEKEND_AM, 0.4)]),
    Persona(
        "casual",
        0.07,
        0.6,
        [(WEEKDAYS, (12, 13, 17, 18, 19), 0.5), (WEEKEND, (10, 11, 12, 13, 14), 0.5)],
        plan_weights=(1.0, 0, 0, 0),
    ),
]


@dataclass
class Sim:
    user: User
    persona: Persona
    joined: date
    active_until: date | None = None  # churned: stopped playing
    fade_start: date | None = None  # fading: when they start slowing down
    circle: list["Sim"] = field(default_factory=list)

    def rate_on(self, day: date) -> float:
        """Expected plays on this day."""
        if day < self.joined:
            return 0.0
        if self.active_until and day > self.active_until:
            return 0.0
        rate = self.persona.per_week / 7
        if self.fade_start and day > self.fade_start:
            weeks = (day - self.fade_start).days / 7
            rate *= max(0.06, math.exp(-weeks / 2.6))
        if self.active_until:
            # churned members also slowed down in the month before leaving
            days_left = (self.active_until - day).days
            if days_left < 35:
                rate *= 0.35 + 0.65 * days_left / 35
        if (day - self.joined).days < 21:
            rate *= 1.2  # new member enthusiasm
        return rate


def level() -> float:
    return min(5.5, max(2.0, round(random.gauss(3.4, 0.7) * 2) / 2))


def pick_slot(persona: Persona, day: date) -> int | None:
    options = [(hours, w) for days, hours, w in persona.slots if day.weekday() in days]
    if not options:
        return None
    hours = random.choices([o[0] for o in options], weights=[o[1] for o in options])[0]
    return random.choice(hours)


_demo_hash: str | None = None


def make_user(db: Session, club: Club, email: str, name: str, role: str, **kw) -> User:
    global _demo_hash
    _demo_hash = _demo_hash or hash_password(DEMO_PASSWORD)  # bcrypt is slow; hash once
    u = User(
        club_id=club.id,
        email=email,
        full_name=name,
        role=role,
        password_hash=_demo_hash,
        qr_token=new_qr_token(),
        **kw,
    )
    db.add(u)
    return u


def seed(db: Session) -> dict:
    random.seed(42)
    now = club_now(TIMEZONE)
    today = now.date()
    start_day = today - timedelta(days=HISTORY_DAYS)

    club = Club(
        name="Riverside Tennis Club",
        timezone=TIMEZONE,
        city="Brooklyn, NY",
        latitude=40.68,
        longitude=-73.97,
        open_hour=7,
        close_hour=22,
        peak_hours={"weekday": [17, 18, 19, 20], "weekend": [8, 9, 10, 11]},
        base_price=40,
        pricing_mode="on",
        min_price=24,
        max_price=68,
        max_surge_pct=35,
        max_discount_pct=30,
        setup_complete=True,
    )
    db.add(club)
    db.flush()

    courts = [
        Court(club_id=club.id, name="Court 1", surface="hard", indoor=False),
        Court(club_id=club.id, name="Court 2", surface="hard", indoor=False),
        Court(club_id=club.id, name="Court 3", surface="clay", indoor=False),
        Court(club_id=club.id, name="Court 4", surface="clay", indoor=False, has_lights=False),
        Court(club_id=club.id, name="Bubble A", surface="hard", indoor=True),
        Court(club_id=club.id, name="Bubble B", surface="hard", indoor=True),
    ]
    db.add_all(courts)
    plans = [
        MembershipPlan(
            club_id=club.id, name="Basic", monthly_price=59, court_discount_pct=0, priority=0
        ),
        MembershipPlan(
            club_id=club.id, name="Plus", monthly_price=99, court_discount_pct=15, priority=1
        ),
        MembershipPlan(
            club_id=club.id,
            name="Premium",
            monthly_price=149,
            court_discount_pct=25,
            priority=2,
            description="Best rates and first pick from the waitlist",
        ),
    ]
    db.add_all(plans)
    db.flush()

    make_user(db, club, "owner@courtiq.demo", "Morgan Reyes", "owner", skill_level=4.0)
    make_user(db, club, "desk@courtiq.demo", "Sasha Kim", "staff", skill_level=3.0)
    coach_specs = [
        ("coach@courtiq.demo", "Daniela Ruiz", "Adults, technique, serve", 75),
        ("marco.coach@courtiq.demo", "Marco Bellini", "Juniors, footwork", 65),
        ("aiko.coach@courtiq.demo", "Aiko Tanaka", "Doubles strategy, clinics", 70),
        ("sam.coach@courtiq.demo", "Sam Okafor", "Competitive players", 90),
    ]
    coaches = []
    for email, name, spec, rate in coach_specs:
        u = make_user(db, club, email, name, "coach", skill_level=5.5)
        db.flush()
        c = Coach(club_id=club.id, user_id=u.id, specialties=spec, hourly_rate=rate)
        db.add(c)
        coaches.append(c)
    db.flush()

    # --- Members ---------------------------------------------------------
    sims: list[Sim] = []
    used_names = set()
    n_members = 250
    persona_pool = random.choices(PERSONAS, weights=[p.share for p in PERSONAS], k=n_members)
    persona_pool[0] = PERSONAS[0]  # the demo member is a regular
    for i, persona in enumerate(persona_pool):
        while True:
            name = f"{random.choice(FIRST)} {random.choice(LAST)}"
            if name not in used_names:
                used_names.add(name)
                break
        if i == 0:
            name, email = "Jordan Lee", "member@courtiq.demo"
        else:
            email = f"{name.lower().replace(' ', '.')}@example.org"
        lvl = 3.5 if i == 0 else level()
        if persona.name == "new":
            joined = today - timedelta(days=random.randint(12, 55))
        elif persona.name == "churned":
            joined = start_day - timedelta(days=random.randint(30, 500))
        else:
            joined = start_day - timedelta(days=random.randint(0, 900))
            if random.random() < 0.15:
                joined = start_day + timedelta(days=random.randint(0, 60))
        days = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        availability = sorted(
            {
                f"{days[d]}:{'morning' if h < 12 else 'afternoon' if h < 17 else 'evening'}"
                for wd, hours, _ in persona.slots
                for d in wd
                for h in hours
            }
        )
        user = make_user(
            db,
            club,
            email,
            name,
            "member",
            skill_level=lvl,
            rating=1000 + lvl * 150 + random.gauss(0, 40),
            phone=f"(718) 555-{random.randint(1000, 9999)}",
            availability=availability,
            play_style=random.choice(STYLES),
            goals=random.choice(GOALS),
            preferred_format=random.choices(["singles", "doubles", "either"], [0.5, 0.2, 0.3])[0],
            league_opt_in=random.random() < 0.35,
        )
        user.created_at = datetime.combine(joined, datetime.min.time()) + timedelta(hours=10)
        sim = Sim(user=user, persona=persona, joined=joined)
        if persona.name == "fading":
            sim.fade_start = today - timedelta(days=random.randint(35, 80))
        if persona.name == "churned":
            sim.active_until = today - timedelta(days=random.randint(45, 130))
        sims.append(sim)
    db.flush()

    # Playing circles: a few regular partners at a similar level.
    for s in sims:
        peers = [
            o
            for o in sims
            if o is not s
            and abs(o.user.skill_level - s.user.skill_level) <= 0.5
            and o.persona.name != "casual"
        ]
        overlap = [o for o in peers if set(o.user.availability) & set(s.user.availability)]
        pool = overlap or peers
        s.circle = random.sample(pool, k=min(len(pool), random.randint(2, 5)))
    # The demo member's regular partner is one of the fading members, so the
    # "regular partner stopped playing" reason shows up on someone they know.
    demo = sims[0]
    faders = [s for s in sims if s.persona.name == "fading"]
    if faders:
        demo.circle[0] = faders[0]

    _memberships(db, sims, plans, start_day, today)

    # --- Bookings ----------------------------------------------------------
    hours = list(range(club.open_hour, club.close_hour))
    occupied: dict[tuple[date, int], set[int]] = defaultdict(set)
    busy: dict[tuple[date, int], set[int]] = defaultdict(set)
    bookings: list[Booking] = []
    turned_away = 0
    discounts = {p.id: p.court_discount_pct for p in plans}
    member_plan = _plan_lookup(db)

    def free_court(day: date, hour: int, indoor_first: bool = False) -> Court | None:
        taken = occupied[(day, hour)]
        order = courts[4:] + courts[:4] if indoor_first else courts
        for c in order:
            if c.id in taken:
                continue
            if not c.has_lights and hour >= 18:
                continue
            return c
        return None

    def add_booking(
        day, hour, court, booker, players, kind, coach=None, title=None, source="member"
    ):
        start = datetime.combine(day, datetime.min.time()).replace(hour=hour)
        pct = discounts.get(member_plan(booker.user.id, day), 0) if booker else 0
        price = club.base_price * (1 - pct / 100)
        breakdown = [{"label": "Member rate", "pct": -pct}] if pct else []
        if coach:
            price += coach.hourly_rate
        b = Booking(
            club_id=club.id,
            court_id=court.id,
            user_id=booker.user.id if booker else None,
            coach_id=coach.id if coach else None,
            start_at=start,
            end_at=start + timedelta(hours=1),
            type=kind,
            title=title,
            capacity=6 if kind == "clinic" else 4,
            base_price=club.base_price,
            price=round(price, 2),
            price_breakdown=breakdown,
            source=source,
        )
        b.created_at = start - timedelta(days=random.randint(0, 6), hours=random.randint(1, 20))
        b.players = [BookingPlayer(user_id=p.user.id) for p in players]
        occupied[(day, hour)].add(court.id)
        for p in players:
            busy[(day, hour)].add(p.user.id)
        bookings.append(b)
        return b

    day = start_day
    while day <= today + timedelta(days=FUTURE_DAYS):
        future_days = (day - today).days
        # People book ahead less the further out you go.
        horizon = 1.0 if future_days <= 0 else max(0.15, 1 - future_days / 12)

        # Weekly clinics: Tuesday 6pm doubles drills, Saturday 1pm juniors.
        for wd, hour, coach, title, lo, hi in (
            (1, 18, coaches[2], "3.0-3.5 Doubles Drills", 2.5, 3.5),
            (5, 13, coaches[1], "Junior Squad", 2.0, 3.5),
            (3, 10, coaches[0], "Morning Cardio Tennis", 2.0, 4.5),
        ):
            if day.weekday() == wd and (court := free_court(day, hour, indoor_first=True)):
                eligible = [
                    s
                    for s in sims
                    if lo <= s.user.skill_level <= hi
                    and s.rate_on(day) > 0
                    and s.user.id not in busy[(day, hour)]
                ]
                group = random.sample(eligible, k=min(len(eligible), random.randint(3, 6)))
                add_booking(day, hour, court, None, group, "clinic", coach, title, "staff")

        order = sims[:]
        random.shuffle(order)
        for s in order:
            if random.random() > s.rate_on(day) * horizon:
                continue
            hour = pick_slot(s.persona, day)
            if hour is None or hour not in hours or s.user.id in busy[(day, hour)]:
                continue
            court = free_court(day, hour)
            if court is None:
                # Peak is full: some try the next hour, the rest give up.
                alt = hour + random.choice((-1, 1))
                if alt in hours and random.random() < 0.45 and s.user.id not in busy[(day, alt)]:
                    court, hour = free_court(day, alt), alt
                if court is None:
                    turned_away += 1
                    continue
            if random.random() < s.persona.lesson_rate:
                coach = random.choice(coaches)
                add_booking(day, hour, court, s, [s], "lesson", coach)
                continue
            roll = random.random()
            partners = [
                p for p in s.circle if p.user.id not in busy[(day, hour)] and p.rate_on(day) > 0
            ]
            if roll < 0.12 or not partners:
                players = [s]  # hitting session / ball machine
            elif roll < 0.27 and len(partners) >= 3:
                players = [s, *random.sample(partners, 3)]
            else:
                players = [s, random.choice(partners)]
            kind = "match" if len(players) == 2 and random.random() < 0.3 else "casual"
            add_booking(day, hour, court, s, players, kind)
        day += timedelta(days=1)

    # --- Outcomes: cancellations, no-shows, check-ins, match results -------
    sim_by_id = {s.user.id: s for s in sims}
    check_ins: list[CheckIn] = []
    played: list[tuple[Booking, User, User]] = []
    for b in bookings:
        booker = sim_by_id.get(b.user_id) if b.user_id else None
        fading = booker is not None and booker.persona.name in ("fading", "churned")
        cancel_p = 0.13 if fading else 0.07
        if random.random() < cancel_p:
            b.status = "cancelled"
            b.cancelled_at = b.start_at - timedelta(hours=random.randint(2, 60))
            continue
        if b.start_at >= now:
            continue
        if random.random() < (0.06 if fading else 0.025):
            b.status = "no_show"
            continue
        b.status = "completed"
        b.paid = random.random() < 0.97
        for p in b.players:
            if random.random() < 0.9:
                check_ins.append(
                    CheckIn(
                        club_id=club.id,
                        user_id=p.user_id,
                        method="qr" if random.random() < 0.85 else "manual",
                        created_at=b.start_at - timedelta(minutes=random.randint(3, 25)),
                        booking=b,
                    )
                )
        if b.type == "match" and len(b.players) == 2:
            a, c = (sim_by_id[p.user_id].user for p in b.players)
            played.append((b, a, c))

    db.add_all(bookings)
    db.flush()
    db.add_all(check_ins)
    played.sort(key=lambda t: t[0].start_at)  # ratings evolve in date order
    matches = [_play_match(club, b, a, c) for b, a, c in played]
    db.add_all(matches)
    db.flush()

    _future_waitlist(db, club, sims, occupied, courts, today, hours)
    _welcome_notes(db, demo.user)
    db.commit()

    return {
        "members": len(sims),
        "bookings": len(bookings),
        "check_ins": len(check_ins),
        "matches": len(matches),
        "turned_away_at_peak": turned_away,
    }


def _memberships(db, sims, plans, start_day, today):
    """Monthly membership history. Fading members are about to lapse; churned ones already have."""
    for s in sims:
        weights = s.persona.plan_weights
        choice = random.choices([None, *plans], weights=weights)[0]
        if choice is None:
            continue
        begin = max(s.joined, start_day - timedelta(days=random.randint(0, 25)))
        if s.persona.name == "churned":
            end_of_history = s.active_until + timedelta(days=random.randint(0, 25))
        elif s.persona.name == "fading":
            end_of_history = today + timedelta(days=random.randint(-10, 24))
        else:
            end_of_history = today + timedelta(days=random.randint(5, 30))
        # Walk back from the last period so the current one ends on end_of_history.
        end = end_of_history
        while end >= begin:
            start = max(begin, end - timedelta(days=30))
            db.add(
                Membership(
                    user_id=s.user.id,
                    plan_id=choice.id,
                    start_date=start,
                    end_date=end,
                    status="active" if end >= today else "expired",
                    auto_renew=True,
                )
            )
            end = start - timedelta(days=1)
    db.flush()
    # Auto-renew is switched off by most leavers and some fading members.
    for s in sims:
        if s.persona.name in ("churned", "fading"):
            last = (
                db.query(Membership)
                .filter_by(user_id=s.user.id)
                .order_by(Membership.end_date.desc())
                .first()
            )
            if last and (s.persona.name == "churned" or random.random() < 0.65):
                last.auto_renew = False
        elif random.random() < 0.08:
            last = (
                db.query(Membership)
                .filter_by(user_id=s.user.id)
                .order_by(Membership.end_date.desc())
                .first()
            )
            if last:
                last.auto_renew = False
    db.flush()


def _plan_lookup(db: Session):
    by_user: dict[int, list[Membership]] = defaultdict(list)
    for m in db.query(Membership).all():
        by_user[m.user_id].append(m)

    def plan_on(user_id: int, day: date) -> int | None:
        for m in by_user.get(user_id, []):
            if m.start_date <= day <= m.end_date:
                return m.plan_id
        return None

    return plan_on


def _play_match(club: Club, booking: Booking, a: User, b: User) -> Match:
    expected_a = 1 / (1 + 10 ** ((b.rating - a.rating) / 400))
    a_wins = random.random() < expected_a
    winner, loser = (a, b) if a_wins else (b, a)
    k = 32
    delta = k * ((1 - expected_a) if a_wins else expected_a)
    winner.rating += delta
    loser.rating -= delta
    a.matches_played += 1
    b.matches_played += 1
    games = random.choice(["6-3 6-4", "6-4 7-5", "7-6 6-4", "6-2 6-3", "4-6 6-3 10-7", "6-1 6-4"])
    return Match(
        club_id=club.id,
        requester_id=a.id,
        opponent_id=b.id,
        status="completed",
        proposed_start=booking.start_at,
        court_id=booking.court_id,
        booking_id=booking.id,
        winner_id=winner.id,
        score_text=games,
        source="member",
    )


def _future_waitlist(db, club, sims, occupied, courts, today, hours):
    """Members waiting on full peak hours in the coming days."""
    candidates = [s for s in sims if s.persona.name in ("regular", "new", "weekend", "fading")]
    for offset in range(1, 6):
        day = today + timedelta(days=offset)
        for hour in hours:
            if len(occupied[(day, hour)]) < len(courts) - 1:
                continue
            for s in random.sample(candidates, k=random.randint(1, 3)):
                db.add(
                    WaitlistEntry(
                        club_id=club.id,
                        user_id=s.user.id,
                        date=day,
                        start_hour=hour,
                        end_hour=hour,
                        status="waiting",
                    )
                )


def _welcome_notes(db: Session, user: User) -> None:
    db.add(
        Notification(
            user_id=user.id,
            kind="welcome",
            title="Welcome to Riverside Tennis Club",
            body="Your QR code is ready under My QR code. Show it at the front desk tablet.",
            link="/app/qr",
            read=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="don't reset the database first")
    args = parser.parse_args()
    if not args.keep:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        stats = seed(db)
    print("Seeded demo club:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"\nSign in with owner@courtiq.demo / {DEMO_PASSWORD} (also desk@, coach@, member@)")


if __name__ == "__main__":
    main()
