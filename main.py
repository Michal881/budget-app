from database import SessionLocal
from models import Expense as ExpenseDB
from models import Category as CategoryDB
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from datetime import date
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

    budget_plans = [
        BudgetPlan(
            category=item["category"],
            year=item["year"],
            month=item["month"],
            planned_amount=item["planned_amount"]
        )
        for item in data.get("budget_plans", [])
    ]

    monthly_limits = [
        MonthlyLimit(
            year=item["year"],
            month=item["month"],
            limit_amount=item["limit_amount"]
        )
        for item in data.get("monthly_limits", [])
    ]


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


load_data()
seed_categories()


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


@app.post("/budget-plans")
def add_budget_plan(plan: BudgetPlan):
    db = SessionLocal()
    try:
        category_exists = db.query(CategoryDB).filter(CategoryDB.name == plan.category).first()
        if not category_exists:
            raise HTTPException(status_code=400, detail="kategoria nie istnieje")

        if plan.month < 1 or plan.month > 12:
            raise HTTPException(status_code=400, detail="nieprawidłowy miesiąc")
        if plan.planned_amount < 0:
            raise HTTPException(status_code=400, detail="planowana kwota nie może być ujemna")

        budget_plans.append(plan)
        save_data()
        return {"message": "dodano plan budżetu", "budget_plans": budget_plans}
    finally:
        db.close()


@app.get("/budget-plans")
def get_budget_plans():
    return budget_plans


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
