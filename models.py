from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base
from database import engine

Base = declarative_base()


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    description = Column(String)
    amount = Column(Float)
    date = Column(String)
    category = Column(String)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    color = Column(String)


class RecurringExpenseTemplate(Base):
    __tablename__ = "recurring_expense_templates"

    id = Column(Integer, primary_key=True, index=True)
    description = Column(String)
    amount = Column(Float)
    category = Column(String)
    frequency = Column(String)
    start_date = Column(String)
    is_active = Column(Boolean, default=True)


class RecurringGenerationLog(Base):
    __tablename__ = "recurring_generation_logs"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("recurring_expense_templates.id"), index=True)
    period_key = Column(String, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), index=True)


Base.metadata.create_all(bind=engine)
