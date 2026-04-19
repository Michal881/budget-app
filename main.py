from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
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

categories = [
    "czynsz",
    "jedzenie",
    "transport",
    "rozrywka",
    "barber"
]


class Category(BaseModel):
    name: str = Field(..., min_length=1)


class Expense(BaseModel):
    amount: float
    category: str
    description: str
    date: date


class BudgetPlan(BaseModel):
    category: str
    year: int
    month: int
    planned_amount: float


expenses = []
budget_plans = []


def save_data():
    data = {
        "expenses": [
            {
                "amount": expense.amount,
                "category": expense.category,
                "description": expense.description,
                "date": expense.date.isoformat(),
            }
            for expense in expenses
        ],
        "budget_plans": [
            {
                "category": plan.category,
                "year": plan.year,
                "month": plan.month,
                "planned_amount": plan.planned_amount,
            }
            for plan in budget_plans
        ],
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_data():
    global expenses, budget_plans

    if not os.path.exists(DATA_FILE):
        expenses = [
            Expense(
                amount=50,
                category="jedzenie",
                description="test",
                date=date(2026, 4, 19)
            ),
            Expense(
                amount=500,
                category="rozrywka",
                description="test",
                date=date(2026, 4, 19)
            )
        ]

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

        save_data()
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    expenses = [
        Expense(
            amount=item["amount"],
            category=item["category"],
            description=item["description"],
            date=date.fromisoformat(item["date"])
        )
        for item in data.get("expenses", [])
    ]

    budget_plans = [
        BudgetPlan(
            category=item["category"],
            year=item["year"],
            month=item["month"],
            planned_amount=item["planned_amount"]
        )
        for item in data.get("budget_plans", [])
    ]


load_data()


@app.get("/")
def root():
    return {"message": "Budget App działa 🚀"}


@app.get("/categories")
def get_categories():
    return categories


@app.post("/categories")
def add_category(category: Category):
    clean_name = category.name.strip()

    if not clean_name:
        return {"message": "nazwa kategorii nie może być pusta"}

    if clean_name in categories:
        return {"message": "kategoria już istnieje", "categories": categories}

    categories.append(clean_name)
    return {"message": "dodano kategorię", "categories": categories}


@app.post("/expenses")
def add_expense(expense: Expense):
    if expense.category not in categories:
        return {"message": "kategoria nie istnieje"}

    expenses.append(expense)
    save_data()
    return {"message": "dodano wydatek", "expenses": expenses}


@app.get("/expenses")
def get_expenses():
    return expenses


@app.delete("/expenses/{expense_index}")
def delete_expense(expense_index: int):
    if expense_index < 0 or expense_index >= len(expenses):
        return {"message": "nieprawidłowy indeks wydatku"}

    deleted = expenses.pop(expense_index)
    save_data()
    return {"message": "usunięto wydatek", "deleted": deleted}


@app.get("/expenses/total")
def get_total_expenses():
    total = sum(expense.amount for expense in expenses)
    return {"total": total}


@app.get("/expenses/total_by_month")
def get_total_by_month(year: int, month: int):
    total = sum(
        expense.amount
        for expense in expenses
        if expense.date.year == year and expense.date.month == month
    )
    return {"year": year, "month": month, "total": total}


@app.get("/expenses/by_category")
def get_expenses_by_category(category: str):
    filtered_expenses = [
        expense for expense in expenses
        if expense.category == category
    ]
    return {"category": category, "expenses": filtered_expenses}


@app.post("/budget-plans")
def add_budget_plan(plan: BudgetPlan):
    if plan.category not in categories:
        return {"message": "kategoria nie istnieje"}

    if plan.month < 1 or plan.month > 12:
        return {"message": "nieprawidłowy miesiąc"}

    if plan.planned_amount < 0:
        return {"message": "planowana kwota nie może być ujemna"}

    budget_plans.append(plan)
    save_data()
    return {"message": "dodano plan budżetu", "budget_plans": budget_plans}


@app.get("/budget-plans")
def get_budget_plans():
    return budget_plans


@app.get("/budget-summary")
def get_budget_summary(category: str, year: int, month: int):
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
        if (
            expense.category == category
            and expense.date.year == year
            and expense.date.month == month
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