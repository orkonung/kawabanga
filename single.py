from flask import Flask, request, jsonify
import threading
import time
import random
import requests

app = Flask(__name__)

freecouriers = []
order_number = 1  # Глобальная переменная для отслеживания номера заказа


# Обработчик для эндпоинта '/add_couriers', Добавляет курьера в список свободных курьеров.
@app.route("/add_couriers", methods=["POST"])
def add_couriers():
    data = request.json
    couriers = data.get("couriers")

    added_couriers = []
    for courier in couriers:
        courier_id = courier.get("id")
        courier_location = courier.get("location")

        # Проверяем, существует ли курьер с таким же id
        existing_courier = next(
            (c for c in freecouriers if c["id"] == courier_id), None
        )

        if existing_courier:
            # Если курьер существует, то проверяем, изменилось ли его местоположение
            if existing_courier["location"] != courier_location:
                # Если местоположение изменилось, обновляем его
                existing_courier["location"] = courier_location
                message = f"Courier with id {courier_id} location updated successfully"
                print(f"Обновлены координаты курьера с id {courier['id']}")
            else:
                # Если местоположение не изменилось, возвращаем сообщение об этом
                message = f"Courier with id {courier_id} location is the same"
                print(f"Координаты курьера с id {courier['id']} не изменились")
        # Если курьер не существует, добавляем его в список
        else:
            freecouriers.append(courier)
            added_couriers.append(courier)
            print(f"Добавлен курьер с id {courier['id']}")
    return jsonify(
        {"message": "Couriers added successfully", "added_couriers": added_couriers}
    )


# Обработчик для эндпоинта '/check_freecouriers', Проверяет список всех свободных курьеров.
@app.route("/check_freecouriers", methods=["GET"])
def get_freecouriers():
    print(freecouriers)
    return jsonify(freecouriers)


# Функция для получения времени, через которое придет курьер на заказ (Парсим 2гис (костыли))
def get_duration_from_2gis(start_coords, end_coords):
    url = f"https://2gis.ru/routeSearch/rsType/car/from/{start_coords[0]},{start_coords[1]}/to/{end_coords[0]},{end_coords[1]}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        html_content = response.text

        print(response.status_code)
        # Находим индекс начала строки "total_duration":
        start_index = html_content.find('"total_duration":')

        if start_index != -1:
            # Находим индекс конца числа
            end_index = html_content.find(",", start_index)
            # Выделяем число после "total_duration":
            duration_str = html_content[
                start_index + len('"total_duration":') : end_index
            ]
            # Преобразуем строку в число
            total_duration = int(duration_str)
        else:
            print("Слово 'total_duration' не найдено на странице.")
        duration = total_duration
        return duration
    else:
        return None


# Функция для получения времени, через которое придет курьер на заказ, используем публичное api osrm или развёртываем сами https://github.com/fossgis-routing-server/osrm-backend
def get_duration_from_osrm(start_coords, end_coords):
    #url = f"http://localhost:4000/route/v1/car/{start_coords[0]},{start_coords[1]};{end_coords[0]},{end_coords[1]}?overview=false"
    url = f"https://router.project-osrm.org/route/v1/car/{start_coords[0]},{start_coords[1]};{end_coords[0]},{end_coords[1]}?overview=false"
    response = requests.get(url)
    data = response.json()
    if response.status_code == 200 and "routes" in data and len(data["routes"]) > 0:
        duration = data["routes"][0]["duration"]
        return duration
    else:
        return None


# Функция для распределения заказов между курьерами
def start_order_processing(orders, nextcouriers, order_number):
    assignments = {}
    order_accepted = threading.Event()  # Создаем объект Event
    order_accepted.clear()  # Устанавливаем состояние события как неактивное (False)
    for order in orders:
        print(
            f" Заказ №{order_number} от {order['from']} до {order['to']}, стоимость {order['cost']}"
        )

    while not order_accepted.is_set() and nextcouriers:
        threads = []  # Список для хранения запущенных потоков
        for orders_group in orders:
            print("Ищем далее")
            order_thread = threading.Thread(
                target=assign_orders,
                args=(orders, nextcouriers, order_number, order_accepted, assignments),
            )
            order_thread.start()
            threads.append(order_thread)
            time.sleep(
                6
            )  # Даем самому ближнему курьеру принять заказ, если в течении 6 секунд не ответит то предлагаем следующему ближнему
    if not order_accepted.is_set() and not nextcouriers:
        for thread in threads:
            print("Ждем окончания всех процессов")
            thread.join()

    return assignments


# Функция для назначения заказа
def assign_orders(orders, nextcouriers, order_number, order_accepted, assignments):
    for order in orders:
        min_duration = float("inf")
        closest_courier = None

        if (
            nextcouriers
        ):  # Если есть ближайшие доступные курьеры, то ищем ту который придет первым
            for courier in nextcouriers:
                duration = get_duration_from_osrm(order["from"], courier["location"])
                print(f"Курьер № {courier['id']}, {duration}")
                if duration is not None and duration < min_duration:
                    min_duration = duration
                    closest_courier = courier
            print(f"Самый ближайший - Курьер № {closest_courier}, {duration}")
    if closest_courier in nextcouriers:  # Удаляем курьер из списка ближайших курьеров
        nextcouriers.remove(closest_courier)
    if closest_courier:  # Если найден ближайший курьер
        order_info = {
            "order": order,
            "duration": min_duration,
            "accepted": False,
            "rejected": False,
        }
        check_and_assign_order(
            closest_courier, order_info, order_number, order_accepted, assignments
        )

    else:
        print("Нет доступных курьеров")


# Логика проверки принятия заказа
def check_and_assign_order(
    closest_courier, order_info, order_number, order_accepted, assignments
):
    #Передаем запрос курьеру
    check_acceptance(closest_courier["id"], order_info, order_number, order_accepted) 

    if order_info["accepted"]:
        order_accepted.set()
        if closest_courier["id"] not in assignments:
            assignments[closest_courier["id"]] = []
        assignments[closest_courier["id"]].append(
            f"Приедет примерно через {int(order_info['duration'] / 60)} мин {round(order_info['duration'] % 60)} сек"
        )
        freecouriers.remove(closest_courier)  # Удаляем из списка свободных курьеров
        print(
            f"Курьер №{closest_courier['id']} принял заказ №{order_number} и будет исключен из списка свободных курьеров"
        )

    elif order_info["rejected"]:
        print(f"Курьер №{closest_courier['id']} отклонил заказ №{order_number}")


# Функция для проверки отлика курьера, имитирует решение курьера о принятии или отклонении заказа.
def check_acceptance(courier_id, order_info, order_number, order_accepted):
    print(f"Предлагаем заказ №{order_number} курьеру №{courier_id}")
    # Генерируем случайную задержку от 4 до 10 секунд
    delay = random.randint(4, 10)
    time.sleep(delay)
    # Если заказ еще не принят кем то, то рандомно принимаем или отклоняем заказ
    if not order_accepted.is_set():
        if random.choice([True, False]):
            order_info["accepted"] = True
        else:
            order_info["rejected"] = True
    else:
        return


# Обработчик для эндпоинта '/assign_orders', посылаем серверу свой заказ, с координатами и ценами
@app.route("/assign_orders", methods=["POST"])
def handle_orders():
    data = request.json
    orders = data.get("orders")

    global freecouriers
    global order_number

    # Вызываем функцию для распределения заказов с указанием текущего номера заказа
    if not freecouriers:
        print("Список свободных курьеров пуст")
        return jsonify({"message": "Нет свободных курьеров"})
    nextcouriers = freecouriers.copy()
    assignments = start_order_processing(orders, nextcouriers, order_number)
    order_number += len(orders)  # Увеличиваем номер заказа для следующих запросов

    if not assignments:
        return "Все отклонили заказ"
    # Возвращает
    else:
        return jsonify(assignments)


# Запуск веб-сервера
if __name__ == "__main__":
    app.run(debug=True)
