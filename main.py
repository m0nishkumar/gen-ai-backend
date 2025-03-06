
import aiohttp
import asyncio
import json

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from pymongo import MongoClient
from bson import ObjectId
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
client = MongoClient("mongodb://localhost:27017/")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_NAME = "restaurant_db"

# Create database and collection
db = client[DB_NAME]
collection = db["placed_orders"]
# Model for the restaurant request parameters


class RestaurantRequest(BaseModel):
    latitude: float
    longitude: float
    restaurant_id: str

class FoodItem(BaseModel):
    id: str
    name: str
    price: float
    quantity: int

class Order(BaseModel):
    foods: List[FoodItem]



@app.post("/create_order/")
async def create_order(order: Order):
    try:
        # Calculate total price
        total_price = sum(food.price * food.quantity for food in order.foods)

        # Create order document
        order_doc = {
            "foods": [food.dict() for food in order.foods],
            "total_price": total_price
        }

        # Insert order into collection
        result = collection.insert_one(order_doc)

        # Return order details with MongoDB-generated ID
        return {
            "order_id": str(result.inserted_id),
            "foods": order.foods,
            "total_price": total_price
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/get_order/{order_id}")
async def get_order(order_id: str):
    try:
        # Find order by ID
        order = collection.find_one({"_id": ObjectId(order_id)})
        
        if order:
            # Convert ObjectId to string for JSON serialization
            order['_id'] = str(order['_id'])
            return order
        else:
            raise HTTPException(status_code=404, detail="Order not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

# Function to fetch restaurant menu data
async def get_restaurant_menu(restaurant_api_url, latitude, longitude, restaurant_id):
    async with aiohttp.ClientSession() as session:
        url = restaurant_api_url(latitude, longitude) + restaurant_id
        print(url)
        
        # Disable SSL verification (for testing purposes only)
        async with session.get(url, ssl=False) as response:  # ssl=False to disable SSL verification
            data = await response.json()
            
            restaurant_data = next((
                x.get('card', {}).get('info')
                for card in data.get('data', {}).get('cards', [])
                if isinstance(card, dict)
                and card.get('card', {}).get('@type') == "type.googleapis.com/swiggy.presentation.food.v2.Restaurant"
            ), None)

            restaurant_offers = next((
                [offer.get('info') for offer in card.get('card', {}).get('gridElements', {}).get('infoWithStyle', {}).get('offers', [])]
                for card in data.get('data', {}).get('cards', [])
                if isinstance(card, dict)
                and card.get('card', {}).get('@type') == "type.googleapis.com/swiggy.gandalf.widgets.v2.GridWidget"
            ), [])

            restaurant_menu = next((
                [
                    card.get('card', {}).get('card')
                    for card in group.get('groupedCard', {}).get('cardGroupMap', {}).get('REGULAR', {}).get('cards', [])
                    if isinstance(card, dict)
                    and card.get('card', {}).get('card', {}).get('@type') == "type.googleapis.com/swiggy.presentation.food.v2.ItemCategory"
                ]
                for group in data.get('data', {}).get('cards', [])
                if isinstance(group, dict) and 'groupedCard' in group
            ), [])

            return restaurant_menu

# FastAPI endpoint to get the restaurant menu
@app.post("/restaurant-menu/")
async def get_menu(request: RestaurantRequest):
    restaurant_api_url = lambda latitude, longitude: f"https://foodfire.onrender.com/api/menu?page-type=REGULAR_MENU&complete-menu=true&lat={latitude}&lng={longitude}&restaurantId="
    
    # Get restaurant data, offers, and menu
    restaurant_menu = await get_restaurant_menu(
        restaurant_api_url, request.latitude, request.longitude, request.restaurant_id
    )
    
    return {
        "restaurant_menu": restaurant_menu
    }


