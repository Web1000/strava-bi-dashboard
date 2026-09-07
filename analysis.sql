-- Example queries against the star schema (fact_activities + dim_activity_type).
SELECT d.activity_type_name, 
       COUNT(*) AS num_activities, 
       ROUND(SUM(f.distance_km), 1) AS total_km,
       ROUND(AVG(f.distance_km), 2) AS avg_km_per_activity
FROM fact_activities f
JOIN dim_activity_type d ON f.activity_type_id = d.activity_type_id
GROUP BY d.activity_type_name
ORDER BY total_km DESC;

-- Monthly Activity Trend: Count of activities and total distance by month
SELECT DATE_TRUNC('month', activity_date) AS month,
       COUNT(*) AS num_activities,
       ROUND(SUM(distance_km), 1) AS total_km
FROM fact_activities
GROUP BY month
ORDER BY month;

--Longest Activities: Retrieve the top 5 longest activities by distance
SELECT activity_name, distance_km, elevation_gain_m
FROM fact_activities
ORDER BY distance_km DESC
LIMIT 5;

-- Find correlation elevation gain and pace
SELECT ROUND(CORR(elevation_gain_m, avg_speed_kmh)::numeric, 3) AS correlation
FROM fact_activities f
JOIN dim_activity_type d ON f.activity_type_id = d.activity_type_id
WHERE d.activity_type_name = 'Run';

--Rolling Average Pace over time (testing window functions)
SELECT activity_date, 
       avg_speed_kmh,
       ROUND(AVG(avg_speed_kmh) OVER (
           ORDER BY activity_date 
           ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
       ), 2) AS rolling_4activity_avg_speed
FROM fact_activities f
JOIN dim_activity_type d ON f.activity_type_id = d.activity_type_id
WHERE d.activity_type_name = 'Run'
ORDER BY activity_date;



