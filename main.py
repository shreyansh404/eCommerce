from fastapi import FastAPI
from pymongo import MongoClient
from typing import Optional, List
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from pprint import pprint
import json
from bson import json_util

# Created a Mongo instance to work with database
mongo = MongoClient("mongodb://127.0.0.1:27017/ecommerce-db")['ecommerce']

# Create an instance of FastAPI
app = FastAPI()

# Item Base Model (For the products bought by the user)
class Item(BaseModel):
    productId: str
    boughtQuantity: int

# User Address Base Model (For the information on user address)
class UserAddress(BaseModel):
    city: str
    country: str
    zip_code: str

# Order Base Model (Structure in which order will be saved in the DB)
class Order(BaseModel):
    createdOn: datetime = Field(default_factory=datetime.now)
    total_amount: int
    user_address: UserAddress
    items: List[Item]

# Base Model for request payload of the create order API
class CreateOrder(BaseModel):
    items: List[Item]
    total_amount: float
    user_address: UserAddress

@app.get("/products")
def get_products(
    offset: int,
    limit: int,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None
):
    """
    Retrieve a paginated list of products with optional price filtering.

    Args:
        offset (int): The number of documents to skip (for pagination).
        limit (int): The maximum number of documents to return (for pagination).
        min_price (Optional[int]): Minimum price filter for products (inclusive).
        max_price (Optional[int]): Maximum price filter for products (inclusive).

    Returns:
        dict: A dictionary containing:
            - "data": A list of product documents matching the criteria.
            - "page": Pagination information including:
                - "total": Total count of documents matching the filter.
                - "limit": Number of documents returned per page.
                - "nextOffset": The offset for the next page of results, or None if no more pages.
                - "prevOffset": The offset for the previous page of results, or None if on the first page.
    """
    agg_pipeline = []

    # Apply filters
    match_stage = {}
    if min_price is not None:
        match_stage["price"] = {"$gte": min_price}
    if max_price is not None:
        match_stage.setdefault("price", {})["$lte"] = max_price

    if match_stage:
        agg_pipeline.append({"$match": match_stage})

    # Pagination and counting
    agg_pipeline.append({
        "$facet": {
            "data": [
                {"$skip": offset},
                {"$limit": limit},
                {
                    "$project": {
                        "id": "$_id",
                        "_id": 0,
                        "name": 1,
                        "price": 1,
                        "quantity": "$available_qty"
                    }
                }
            ],
            "page": [
                {"$count": "total_count"}
            ]
        }
    })

    result = list(mongo['products'].aggregate(agg_pipeline))

    # Extract pagination info
    data = result[0]['data']
    total_count = result[0]['page'][0]['total_count'] if result[0]['page'] else 0
    next_offset = offset + limit if offset + limit < total_count else None
    prev_offset = offset - limit if offset > 0 else None

    return {
        "data": data,
        "page": {
            "total": total_count,
            "limit": limit,
            "nextOffset": next_offset,
            "prevOffset": prev_offset
        }
    }

@app.post("/orders", response_model=Order)
def create_order(order_data: CreateOrder):
    """
    Create a new order and insert it into the orders collection.

    Args:
        order_data (CreateOrder): The order data including items, total amount, and user address.

    Returns:
        Order: The created order object including the generated order ID.
    """
    # Convert ObjectId to str (because of pydantic version compatibility)
    for item in order_data.items:
        item.productId = str(item.productId)

    # Create the order object
    order_obj = Order(
        id=str(mongo['orders'].insert_one(order_data.dict()).inserted_id),
        items=order_data.items,
        total_amount=order_data.total_amount,
        user_address=order_data.user_address
    )

    return order_obj