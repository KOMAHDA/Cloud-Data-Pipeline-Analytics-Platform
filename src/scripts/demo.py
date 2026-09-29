import json
from src.database import SessionLocal  # Импорт фабрики сессий
from src.crud import user, dataset, algorithm, pipeline, job

def main():
    # Открываем сессию
    db = SessionLocal()
    
    try:
        print("--- 1. Создание пользователей ---")
        admin = user.create_user(db, email="admin@example.com", hashed_password="hash_admin", role="admin")
        client = user.create_user(db, email="client@example.com", hashed_password="hash_client", role="client")
        print(f"Создан админ ID: {admin.id}, Клиент ID: {client.id}")

        print("\n--- 2. Регистрация алгоритмов ---")
        algo1 = algorithm.create_algorithm(
            db, code="alg_clean", name="Очистка данных", 
            grpc_handler="handler_clean", default_params={"drop_na": True}
        )
        algo2 = algorithm.create_algorithm(
            db, code="alg_ml", name="Обучение модели", 
            grpc_handler="handler_ml", default_params={"epochs": 10}
        )
        print(f"Созданы алгоритмы: {algo1.name}, {algo2.name}")

        print("\n--- 3. Создание датасета ---")
        ds = dataset.create_dataset(
            db, user_id=client.id, name="Raw Data", 
            file_path="/data/raw.csv", row_count=1000, file_size_bytes=2048
        )
        print(f"Создан датасет: {ds.name} (ID: {ds.id})")

        print("\n--- 4. Сборка конвейера (Pipeline) ---")
        pipe = pipeline.create_pipeline(
            db, title="My First Pipeline", description="Test pipeline", 
            created_by=client.id, is_published=True
        )
        
        # Добавляем шаги
        pipeline.add_step_to_pipeline(db, pipeline_id=pipe.id, algorithm_id=algo1.id, step_order=1, step_params={"drop_na": True})
        pipeline.add_step_to_pipeline(db, pipeline_id=pipe.id, algorithm_id=algo2.id, step_order=2, step_params={"epochs": 5})
        
        # Проверяем joinedload
        pipe_details = pipeline.get_pipeline_details(db, pipe.id)
        print(f"Конвейер '{pipe_details.title}' содержит шагов: {len(pipe_details.steps)}")
        for step in pipe_details.steps:
            print(f"  - Шаг {step.step_order}: {step.algorithm.name} с параметрами {step.step_params}")

        print("\n--- 5. Запуск задачи (Job) ---")
        # Создаем задачу
        new_job = job.create_job(db, user_id=client.id, dataset_id=ds.id, pipeline_id=pipe.id)
        print(f"Задача создана. Статус: {new_job.status}")

        # Переводим в RUNNING (шаг 1)
        job.update_job_status(db, job_id=new_job.id, status="RUNNING", current_step=1)
        print(f"Задача обновлена. Статус: RUNNING, Шаг: 1")

        # Завершаем (COMPLETED) с result_data
        result_payload = {"accuracy": 0.95, "model_path": "/models/model_v1.pkl"}
        job.update_job_status(
            db, job_id=new_job.id, status="COMPLETED", 
            current_step=2, result_data=result_payload
        )
        
        # Финальная проверка
        final_job = db.query(job.ProcessingJob).filter(job.ProcessingJob.id == new_job.id).first()
        print(f"Задача завершена. Статус: {final_job.status}")
        print(f"Результат (JSON): {json.dumps(final_job.result_data)}")

    except Exception as e:
        print(f"Ошибка выполнения: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()