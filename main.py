from database import SessionLocal
from models import Category as CategoryDB
from models import Expense as ExpenseDB
from models import RecurringExpenseTemplate as RecurringExpenseTemplateDB
from models import RecurringGenerationLog as RecurringGenerationLogDB
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from datetime import date, timedelta
import calendar
import json
import os
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = "data.json"


class ExpenseCreate(BaseModel):
    amount: float = Field(gt=0, le=1_000_000)
    category: str
    description: str
    date: date


class ExpenseUpdate(BaseModel):
    amount: float = Field(gt=0, le=1_000_000)
    category: str
    description: str
    date: date


class CategoryCreate(BaseModel):
    name: str
    color: str


class BudgetPlan(BaseModel):
    category: str
    year: int
    month: int
    planned_amount: float


class MonthlyLimit(BaseModel):
    year: int
    month: int
    limit_amount: float = Field(ge=0)


class RecurringTemplateCreate(BaseModel):
    description: str
    amount: float = Field(gt=0, le=1_000_000)
    category: str
    frequency: str = Field(pattern="^(monthly|weekly)$")
    start_date: date
    is_active: bool = True


class RecurringTemplateUpdate(BaseModel):
    description: str | None = None
    amount: float | None = Field(default=None, gt=0, le=1_000_000)
    category: str | None = None
    frequency: str | None = Field(default=None, pattern="^(monthly|weekly)$")
    start_date: date | None = None
    is_active: bool | None = None


budget_plans = []
monthly_limits = []
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def validate_non_empty_text(value: str, field_name: str) -> str:
    clean_value = value.strip()
    if not clean_value:
        raise HTTPException(status_code=400, detail=f"{field_name} nie może być puste")
    return clean_value


def validate_hex_color(value: str) -> str:
    if not HEX_COLOR_RE.fullmatch(value):
        raise HTTPException(status_code=400, detail="kolor musi mieć format #RRGGBB")
    return value.lower()


def save_data():
    data = {
        "budget_plans": [
            {
                "category": plan.category,
                "year": plan.year,
                "month": plan.month,
                "planned_amount": plan.planned_amount,
            }
            for plan in budget_plans
        ],
        "monthly_limits": [
            {
                "year": item.year,
                "month": item.month,
                "limit_amount": item.limit_amount,
            }
            for item in monthly_limits
        ],
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_data():
    global budget_plans, monthly_limits

    if not os.path.exists(DATA_FILE):
        budget_plans = [
            BudgetPlan(
                category="jedzenie",
                year=2026,
                month=4,
                planned_amount=300
            ),
            BudgetPlan(
                category="rozrywka",
                year=2026,
                month=4,
                planned_amount=400
            )
        ]

        monthly_limits = [
            MonthlyLimit(
                year=2026,
                month=4,
                limit_amount=2000
            )
        ]

        save_data()
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    latest_plans_by_key = {}
    for item in data.get("budget_plans", []):
        plan = BudgetPlan(
            category=item["category"],
            year=item["year"],
            month=item["month"],
            planned_amount=item["planned_amount"]
        )
        plan_key = (plan.category, plan.year, plan.month)
        latest_plans_by_key[plan_key] = plan

    budget_plans = list(latest_plans_by_key.values())

    monthly_limits = [
        MonthlyLimit(
            year=item["year"],
            month=item["month"],
            limit_amount=item["limit_amount"]
        )
        for item in data.get("monthly_limits", [])
    ]

    save_data()


def validate_year_month(year: int, month: int):
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="nieprawidłowy miesiąc")


def upsert_budget_plan(plan: BudgetPlan):
    global budget_plans

    updated = False
    next_plans = []

    for existing in budget_plans:
        same_key = (
            existing.category == plan.category
            and existing.year == plan.year
            and existing.month == plan.month
        )

        if same_key:
            next_plans.append(plan)
            updated = True
        else:
            next_plans.append(existing)

    if not updated:
        next_plans.append(plan)

    budget_plans = next_plans

    return updated


def seed_categories():
    db = SessionLocal()
    try:
        existing = db.query(CategoryDB).count()
        if existing == 0:
            defaults = [
                {"name": "czynsz", "color": "#7c8798"},
                {"name": "jedzenie", "color": "#34a853"},
                {"name": "transport", "color": "#1a73e8"},
                {"name": "rozrywka", "color": "#a142f4"},
                {"name": "barber", "color": "#f29900"},
            ]

            for item in defaults:
                db.add(CategoryDB(name=item["name"], color=item["color"]))

            db.commit()
    finally:
        db.close()


def ensure_recurring_generation_unique_index():
    db = SessionLocal()
    try:
        db.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_recurring_generation_template_period "
            "ON recurring_generation_logs (template_id, period_key)"
        ))
        db.commit()
    finally:
        db.close()


def serialize_recurring_template(template: RecurringExpenseTemplateDB):
    return {
        "id": template.id,
        "description": template.description,
        "amount": template.amount,
        "category": template.category,
        "frequency": template.frequency,
        "start_date": template.start_date,
        "is_active": template.is_active,
    }


def get_monthly_due_date(template_start: date, year: int, month: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    target_day = min(template_start.day, last_day)
    return date(year, month, target_day)


def get_weekly_due_date(template_start: date, target_date: date) -> date | None:
    if target_date < template_start:
        return None

    start_of_week = target_date - timedelta(days=target_date.weekday())
    due_date = start_of_week + timedelta(days=template_start.weekday())

    if due_date < template_start:
        return None

    if due_date > target_date:
        return None

    return due_date


def generate_recurring_expenses(target_date: date):
    db = SessionLocal()
    try:
        templates = (
            db.query(RecurringExpenseTemplateDB)
            .filter(RecurringExpenseTemplateDB.is_active == True)
            .all()
        )

        generated_count = 0
        skipped_count = 0

        for template in templates:
            template_start = date.fromisoformat(template.start_date)
            if template_start > target_date:
                skipped_count += 1
                continue

            if template.frequency == "monthly":
                period_key = f"monthly:{target_date.year:04d}-{target_date.month:02d}"
                due_date = get_monthly_due_date(template_start, target_date.year, target_date.month)
                if due_date > target_date:
                    skipped_count += 1
                    continue
            else:
                iso_year, iso_week, _ = target_date.isocalendar()
                period_key = f"weekly:{iso_year:04d}-W{iso_week:02d}"
                due_date = get_weekly_due_date(template_start, target_date)
                if due_date is None:
                    skipped_count += 1
                    continue

            already_generated = (
                db.query(RecurringGenerationLogDB)
                .filter(
                    RecurringGenerationLogDB.template_id == template.id,
                    RecurringGenerationLogDB.period_key == period_key,
                )
                .first()
            )

            if already_generated:
                skipped_count += 1
                continue

            expense = ExpenseDB(
                description=template.description,
                amount=template.amount,
                date=due_date.isoformat(),
                category=template.category,
            )
            db.add(expense)
            db.flush()

            db.add(
                RecurringGenerationLogDB(
                    template_id=template.id,
                    period_key=period_key,
                    expense_id=expense.id,
                )
            )
            generated_count += 1

        db.commit()

        return {
            "target_date": target_date.isoformat(),
            "generated": generated_count,
            "skipped": skipped_count,
        }
    finally:
        db.close()


load_data()
seed_categories()
ensure_recurring_generation_unique_index()


@app.get("/")
def serve_index():
    return FileResponse("index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/categories")
def get_categories():
    db = SessionLocal()
    try:
        categories = db.query(CategoryDB).order_by(CategoryDB.name).all()
        return [
            {
                "id": c.id,
                "name": c.name,
                "color": c.color
            }
            for c in categories
        ]
    finally:
        db.close()


@app.post("/categories")
def add_category(category: CategoryCreate):
    clean_name = validate_non_empty_text(category.name, "nazwa kategorii")
    clean_color = validate_hex_color(category.color)

    db = SessionLocal()
    try:
        existing = db.query(CategoryDB).filter(CategoryDB.name == clean_name).first()
        if existing:
            raise HTTPException(status_code=409, detail="kategoria już istnieje")

        new_category = CategoryDB(name=clean_name, color=clean_color)
        db.add(new_category)
        db.commit()
        db.refresh(new_category)

        return {
            "message": "dodano kategorię",
            "category": {
                "id": new_category.id,
                "name": new_category.name,
                "color": new_category.color
            }
        }
    finally:
        db.close()


@app.delete("/categories/{category_name}")
def delete_category(category_name: str):
    clean_name = validate_non_empty_text(category_name, "nazwa kategorii")

    db = SessionLocal()
    try:
        category = db.query(CategoryDB).filter(CategoryDB.name == clean_name).first()

        if not category:
            raise HTTPException(status_code=404, detail="nie znaleziono kategorii")

        has_expenses = db.query(ExpenseDB).filter(ExpenseDB.category == clean_name).first()
        if has_expenses:
            raise HTTPException(
                status_code=409,
                detail="nie można usunąć kategorii, bo są do niej przypisane wydatki"
            )

        has_templates = (
            db.query(RecurringExpenseTemplateDB)
            .filter(RecurringExpenseTemplateDB.category == clean_name)
            .first()
        )
        if has_templates:
            raise HTTPException(
                status_code=409,
                detail="nie można usunąć kategorii, bo są do niej przypisane cykliczne wydatki"
            )

        db.delete(category)
        db.commit()

        return {"message": "usunięto kategorię"}
    finally:
        db.close()


@app.post("/expenses")
def add_expense(expense: ExpenseCreate):
    clean_description = validate_non_empty_text(expense.description, "opis")

    db = SessionLocal()
    try:
        category_exists = db.query(CategoryDB).filter(CategoryDB.name == expense.category).first()
        if not category_exists:
            raise HTTPException(status_code=400, detail="kategoria nie istnieje")

        new_expense = ExpenseDB(
            description=clean_description,
            amount=expense.amount,
            date=expense.date.isoformat(),
            category=expense.category
        )

        db.add(new_expense)
        db.commit()
        db.refresh(new_expense)

        return {
            "message": "dodano wydatek",
            "expense": {
                "id": new_expense.id,
                "description": new_expense.description,
                "amount": new_expense.amount,
                "date": new_expense.date,
                "category": new_expense.category
            }
        }
    finally:
        db.close()


@app.get("/expenses")
def get_expenses(
    category: str | None = None,
    year: int | None = None,
    month: int | None = Query(default=None, ge=1, le=12),
    sort_by: str = Query(default="date", pattern="^(date|amount)$"),
    sort_order: str | None = Query(default=None, pattern="^(asc|desc)$")
):
    db = SessionLocal()
    try:
        query = db.query(ExpenseDB)

        if category:
            query = query.filter(ExpenseDB.category == category)

        if year is not None and month is not None:
            month_prefix = f"{year:04d}-{month:02d}"
            query = query.filter(ExpenseDB.date.like(f"{month_prefix}-%"))
        elif (year is None) != (month is None):
            raise HTTPException(
                status_code=400,
                detail="podaj jednocześnie rok i miesiąc do filtrowania"
            )

        if sort_by == "amount":
            effective_order = sort_order or "asc"
            if effective_order == "desc":
                query = query.order_by(ExpenseDB.amount.desc())
            else:
                query = query.order_by(ExpenseDB.amount.asc())
        else:
            effective_order = sort_order or "desc"
            if effective_order == "asc":
                query = query.order_by(ExpenseDB.date.asc())
            else:
                query = query.order_by(ExpenseDB.date.desc())

        expenses = query.all()

        return [
            {
                "id": e.id,
                "description": e.description,
                "amount": e.amount,
                "date": e.date,
                "category": e.category
            }
            for e in expenses
        ]
    finally:
        db.close()


@app.get("/expenses/by_category")
def get_expenses_by_category(category: str):
    db = SessionLocal()
    try:
        expenses = db.query(ExpenseDB).filter(ExpenseDB.category == category).all()

        return {
            "category": category,
            "expenses": [
                {
                    "id": e.id,
                    "description": e.description,
                    "amount": e.amount,
                    "date": e.date,
                    "category": e.category
                }
                for e in expenses
            ]
        }
    finally:
        db.close()


@app.put("/expenses/{expense_id}")
def update_expense(expense_id: int, expense_update: ExpenseUpdate):
    clean_description = validate_non_empty_text(expense_update.description, "opis")

    db = SessionLocal()
    try:
        category_exists = db.query(CategoryDB).filter(CategoryDB.name == expense_update.category).first()
        if not category_exists:
            raise HTTPException(status_code=400, detail="kategoria nie istnieje")

        expense = db.query(ExpenseDB).filter(ExpenseDB.id == expense_id).first()

        if not expense:
            raise HTTPException(status_code=404, detail="nie znaleziono wydatku")

        expense.description = clean_description
        expense.amount = expense_update.amount
        expense.date = expense_update.date.isoformat()
        expense.category = expense_update.category

        db.commit()
        db.refresh(expense)

        return {
            "message": "zaktualizowano wydatek",
            "expense": {
                "id": expense.id,
                "description": expense.description,
                "amount": expense.amount,
                "date": expense.date,
                "category": expense.category
            }
        }
    finally:
        db.close()


@app.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int):
    db = SessionLocal()
    try:
        expense = db.query(ExpenseDB).filter(ExpenseDB.id == expense_id).first()

        if not expense:
            raise HTTPException(status_code=404, detail="nie znaleziono wydatku")

        db.delete(expense)
        db.commit()

        return {"message": "usunięto wydatek", "deleted_id": expense_id}
    finally:
        db.close()


@app.get("/expenses/total")
def get_total_expenses():
    db = SessionLocal()
    try:
        expenses = db.query(ExpenseDB).all()
        total = sum(expense.amount for expense in expenses)
        return {"total": total}
    finally:
        db.close()


@app.get("/expenses/total_by_month")
def get_total_by_month(year: int, month: int):
    db = SessionLocal()
    try:
        expenses = db.query(ExpenseDB).all()

        total = 0
        for expense in expenses:
            expense_date = date.fromisoformat(expense.date)
            if expense_date.year == year and expense_date.month == month:
                total += expense.amount

        return {"year": year, "month": month, "total": total}
    finally:
        db.close()


@app.post("/recurring-expenses")
def add_recurring_template(template: RecurringTemplateCreate):
    clean_description = validate_non_empty_text(template.description, "opis")

    db = SessionLocal()
    try:
        category_exists = db.query(CategoryDB).filter(CategoryDB.name == template.category).first()
        if not category_exists:
            raise HTTPException(status_code=400, detail="kategoria nie istnieje")

        recurring = RecurringExpenseTemplateDB(
            description=clean_description,
            amount=template.amount,
            category=template.category,
            frequency=template.frequency,
            start_date=template.start_date.isoformat(),
            is_active=template.is_active,
        )

        db.add(recurring)
        db.commit()
        db.refresh(recurring)

        return {
            "message": "dodano cykliczny wydatek",
            "template": serialize_recurring_template(recurring),
        }
    finally:
        db.close()


@app.get("/recurring-expenses")
def get_recurring_templates(include_inactive: bool = False):
    db = SessionLocal()
    try:
        query = db.query(RecurringExpenseTemplateDB)
        if not include_inactive:
            query = query.filter(RecurringExpenseTemplateDB.is_active == True)

        templates = query.order_by(RecurringExpenseTemplateDB.id.desc()).all()
        return [serialize_recurring_template(template) for template in templates]
    finally:
        db.close()


@app.put("/recurring-expenses/{template_id}")
def update_recurring_template(template_id: int, payload: RecurringTemplateUpdate):
    db = SessionLocal()
    try:
        template = db.query(RecurringExpenseTemplateDB).filter(RecurringExpenseTemplateDB.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="nie znaleziono cyklicznego wydatku")

        if payload.description is not None:
            template.description = validate_non_empty_text(payload.description, "opis")

        if payload.amount is not None:
            template.amount = payload.amount

        if payload.category is not None:
            category_exists = db.query(CategoryDB).filter(CategoryDB.name == payload.category).first()
            if not category_exists:
                raise HTTPException(status_code=400, detail="kategoria nie istnieje")
            template.category = payload.category

        if payload.frequency is not None:
            template.frequency = payload.frequency

        if payload.start_date is not None:
            template.start_date = payload.start_date.isoformat()

        if payload.is_active is not None:
            template.is_active = payload.is_active

        db.commit()
        db.refresh(template)

        return {
            "message": "zaktualizowano cykliczny wydatek",
            "template": serialize_recurring_template(template),
        }
    finally:
        db.close()


@app.post("/recurring-expenses/{template_id}/deactivate")
def deactivate_recurring_template(template_id: int):
    db = SessionLocal()
    try:
        template = db.query(RecurringExpenseTemplateDB).filter(RecurringExpenseTemplateDB.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="nie znaleziono cyklicznego wydatku")

        template.is_active = False
        db.commit()

        return {"message": "dezaktywowano cykliczny wydatek"}
    finally:
        db.close()


@app.delete("/recurring-expenses/{template_id}")
def delete_recurring_template(template_id: int):
    db = SessionLocal()
    try:
        template = db.query(RecurringExpenseTemplateDB).filter(RecurringExpenseTemplateDB.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="nie znaleziono cyklicznego wydatku")

        db.query(RecurringGenerationLogDB).filter(RecurringGenerationLogDB.template_id == template_id).delete()
        db.delete(template)
        db.commit()

        return {"message": "usunięto cykliczny wydatek"}
    finally:
        db.close()


@app.post("/recurring-expenses/generate")
def generate_recurring(target_date: date | None = None):
    generation_date = target_date or date.today()
    return generate_recurring_expenses(generation_date)


@app.post("/budget-plans")
def add_budget_plan(plan: BudgetPlan):
    db = SessionLocal()
    try:
        category_exists = db.query(CategoryDB).filter(CategoryDB.name == plan.category).first()
        if not category_exists:
            raise HTTPException(status_code=400, detail="kategoria nie istnieje")

        validate_year_month(plan.year, plan.month)
        if plan.planned_amount < 0:
            raise HTTPException(status_code=400, detail="planowana kwota nie może być ujemna")

        was_updated = upsert_budget_plan(plan)
        save_data()
        return {
            "message": "zaktualizowano plan budżetu" if was_updated else "dodano plan budżetu",
            "plan": plan,
            "updated": was_updated
        }
    finally:
        db.close()


@app.get("/budget-plans")
def get_budget_plans():
    return budget_plans


@app.get("/budget-plans/month")
def get_budget_plans_for_month(year: int, month: int):
    validate_year_month(year, month)

    return [
        plan
        for plan in budget_plans
        if plan.year == year and plan.month == month
    ]


@app.delete("/budget-plans")
def delete_budget_plan(category: str, year: int, month: int):
    global budget_plans

    clean_category = validate_non_empty_text(category, "kategoria")
    validate_year_month(year, month)

    before_count = len(budget_plans)
    budget_plans = [
        plan
        for plan in budget_plans
        if not (
            plan.category == clean_category
            and plan.year == year
            and plan.month == month
        )
    ]

    if len(budget_plans) == before_count:
        raise HTTPException(status_code=404, detail="nie znaleziono planu budżetu")

    save_data()
    return {"message": "usunięto plan budżetu"}


@app.get("/budget-summary")
def get_budget_summary(category: str, year: int, month: int):
    db = SessionLocal()
    try:
        expenses = db.query(ExpenseDB).all()

        planned = 0
        spent = 0

        for plan in budget_plans:
            if (
                plan.category == category
                and plan.year == year
                and plan.month == month
            ):
                planned = plan.planned_amount

        for expense in expenses:
            expense_date = date.fromisoformat(expense.date)
            if (
                expense.category == category
                and expense_date.year == year
                and expense_date.month == month
            ):
                spent += expense.amount

        remaining = planned - spent

        return {
            "category": category,
            "year": year,
            "month": month,
            "planned": planned,
            "spent": spent,
            "remaining": remaining
        }
    finally:
        db.close()


@app.post("/monthly-limit")
def set_monthly_limit(limit: MonthlyLimit):
    if limit.month < 1 or limit.month > 12:
        raise HTTPException(status_code=400, detail="nieprawidłowy miesiąc")

    global monthly_limits

    monthly_limits = [
        item for item in monthly_limits
        if not (item.year == limit.year and item.month == limit.month)
    ]

    monthly_limits.append(limit)
    save_data()

    return {"message": "zapisano limit miesięczny", "limit": limit}


@app.get("/monthly-limit")
def get_monthly_limit(year: int, month: int):
    limit_value = 0

    for item in monthly_limits:
        if item.year == year and item.month == month:
            limit_value = item.limit_amount

    return {
        "year": year,
        "month": month,
        "limit": limit_value
    }


@app.get("/monthly-summary")
def get_monthly_summary(year: int, month: int):
    db = SessionLocal()
    try:
        expenses = db.query(ExpenseDB).all()

        spent = 0
        for expense in expenses:
            expense_date = date.fromisoformat(expense.date)
            if expense_date.year == year and expense_date.month == month:
                spent += expense.amount

        limit_value = 0
        for item in monthly_limits:
            if item.year == year and item.month == month:
                limit_value = item.limit_amount

        remaining = limit_value - spent

        return {
            "year": year,
            "month": month,
            "limit": limit_value,
            "spent": spent,
            "remaining": remaining
        }
    finally:
        db.close()
