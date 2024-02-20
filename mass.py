from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# Функция для получения расстояния и времени прибытия курьера на заказ (OSRM API)
def get_distance_from_osrm(start_coords, end_coords):
    #url = f"http://localhost:4000/route/v1/car/{start_coords[0]},{start_coords[1]};{end_coords[0]},{end_coords[1]}?overview=false"
    url = f"https://router.project-osrm.org/route/v1/car/{start_coords[0]},{start_coords[1]};{end_coords[0]},{end_coords[1]}?overview=false"
    response = requests.get(url)
    data = response.json()
    if response.status_code == 200 and 'routes' in data and len(data['routes']) > 0:
        duration = data['routes'][0]['duration']
        return duration
    else:
        return None

# Функция для распределения заказов между курьерами
def assign_orders(orders, couriers):
    assignments = {}
    for order in orders:
        print(f" Заказ №{order['id']} от {order['from']} до {order['to']}, стоимость {order['cost']}")
        min_duration = float('+inf')
        closest_courier = None
        for courier in couriers:
            duration = get_distance_from_osrm(courier['location'], order['from'])
            if duration is not None and duration < min_duration:
                min_duration = duration
                closest_courier = courier
        print(f"На заказ №{order['id']} первым придёт Курьер № {closest_courier['id']}, примерно через  {int(min_duration / 60)} мин {round(min_duration % 60)} сек")
        if closest_courier['id'] not in assignments:
            assignments[closest_courier['id']] = []
        order_info = {'order': order, 'duration': min_duration}   
        assignments[closest_courier['id']].append(order['id'])
    return assignments

# Обработчик для эндпоинта '/assign_orders'
@app.route('/assign_orders', methods=['POST'])
def handle_orders():
    data = request.json
    orders = data.get('orders')
    couriers = data.get('couriers')
    assignments = assign_orders(orders, couriers)
    return assignments

# Запуск веб-сервера
if __name__ == '__main__':
    app.run(debug=True)
