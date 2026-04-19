from database import SessionLocal
from models import Expense as ExpenseDB
from models import Category as CategoryDB
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import date
import json
import os

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
    amount: float
    category: str
    description: str
    date: date


class ExpenseUpdate(BaseModel):
    amount: float
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
    limit_amount: float


budget_plans = []
monthly_limits = []


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
    clean_name = category.name.strip()

    if not clean_name:
        return {"message": "nazwa kategorii nie może być pusta"}

    db = SessionLocal()
    try:
        existing = db.query(CategoryDB).filter(CategoryDB.name == clean_name).first()
        if existing:
            return {"message": "kategoria już istnieje"}

        new_category = CategoryDB(name=clean_name, color=category.color)
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
    db = SessionLocal()
    try:
        category = db.query(CategoryDB).filter(CategoryDB.name == category_name).first()

        if not category:
            return {"message": "nie znaleziono kategorii"}

        has_expenses = db.query(ExpenseDB).filter(ExpenseDB.category == category_name).first()
        if has_expenses:
            return {"message": "nie można usunąć kategorii, bo są do niej przypisane wydatki"}

        db.delete(category)
        db.commit()

        return {"message": "usunięto kategorię"}
    finally:
        db.close()


@app.post("/expenses")
def add_expense(expense: ExpenseCreate):
    db = SessionLocal()
    try:
        category_exists = db.query(CategoryDB).filter(CategoryDB.name == expense.category).first()
        if not category_exists:
            return {"message": "kategoria nie istnieje"}

        new_expense = ExpenseDB(
            description=expense.description,
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
def get_expenses():
    db = SessionLocal()
    try:
        expenses = db.query(ExpenseDB).all()

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
    db = SessionLocal()
    try:
        category_exists = db.query(CategoryDB).filter(CategoryDB.name == expense_update.category).first()
        if not category_exists:
            return {"message": "kategoria nie istnieje"}

        expense = db.query(ExpenseDB).filter(ExpenseDB.id == expense_id).first()

        if not expense:
            return {"message": "nie znaleziono wydatku"}

        expense.description = expense_update.description
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
            return {"message": "nie znaleziono wydatku"}

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
            return {"message": "kategoria nie istnieje"}

        if plan.month < 1 or plan.month > 12:
            return {"message": "nieprawidłowy miesiąc"}

        if plan.planned_amount < 0:
            return {"message": "planowana kwota nie może być ujemna"}

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
        return {"message": "nieprawidłowy miesiąc"}

    if limit.limit_amount < 0:
        return {"message": "limit nie może być ujemny"}

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