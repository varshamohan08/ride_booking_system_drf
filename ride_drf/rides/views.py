from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rides.serializers import RideSerializer
from user_app.models import UserDetails, vehicle_type
from .models import Ride, RideStatus
from django.core.exceptions import PermissionDenied

from geopy.distance import geodesic
from datetime import datetime
from ast import literal_eval

def calculate_distance_time(point1, point2, speed_kmph=20):
    
    distance = geodesic(point1, point2).kilometers

    time_hours = distance / speed_kmph

    time_seconds = int(time_hours * 60 * 60)

    hours, remainder = divmod(time_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    return distance, hours, minutes, seconds

{
    "pickup_location" : {"latitude" : 9.581331590728096, "longitude" : 76.63346969672654},
    "dropoff_location" : {"latitude" : 10.301818563381353, "longitude" : 76.3329825120758}
}

class requestRide(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            pickup_location = request.data.get('pickup_location')
            dropoff_location = request.data.get('dropoff_location')
            drivers = UserDetails.objects.filter(user_type = 'Driver', available = True).values('name', 'location', 'vehicle_type')
            vehicle_types = vehicle_type.objects.values()

            vehicle_dict = {}

            for each_vehicle_type in vehicle_types:
                drivers = UserDetails.objects.filter(user_type = 'Driver', vehicle_type_id = each_vehicle_type["id"], available = True).values('user', 'name', 'location', 'vehicle_type')

                for each_driver in drivers:

                    location_dict = literal_eval(each_driver['location'])

                    point1 = (location_dict['latitude'], location_dict['longitude'])
                    point2 = (pickup_location['latitude'], pickup_location['longitude'])

                    distance, hours, minutes, seconds = calculate_distance_time(point1, point2)

                    time_taken = f"{hours}h {minutes}min {seconds}sec"

                    total_minutes = hours * 60 + minutes + seconds / 60

                    if each_vehicle_type['id'] in vehicle_dict.keys() and vehicle_dict[each_vehicle_type['id']]['distance'] > distance:

                        amount = round(each_vehicle_type['fare'] + (each_vehicle_type['cost_per_km'] * distance) + (each_vehicle_type['cost_per_min'] * total_minutes))
                        if amount < each_vehicle_type['min_fare']:
                            amount = each_vehicle_type['min_fare']

                        vehicle_dict[each_vehicle_type['id']] = {
                            'distance': distance, 
                            'distance_km': str(distance) + 'km', 
                            'time' : time_taken,
                            'type' : each_vehicle_type['type'],
                            'driver' : each_driver['user'],
                            'amount' :amount
                        }
                        
                    else:

                        amount = round(each_vehicle_type['fare'] + (each_vehicle_type['cost_per_km'] * distance) + (each_vehicle_type['cost_per_min'] * total_minutes))
                        if amount < each_vehicle_type['min_fare']:
                            amount = each_vehicle_type['min_fare']

                        vehicle_dict[each_vehicle_type['id']] = {
                            'distance': distance, 
                            'distance_km': str(distance) + 'km', 
                            'time' : time_taken,
                            'type' : each_vehicle_type['type'],
                            'driver' : each_driver['user'],
                            'amount' :amount
                        }

            return Response(vehicle_dict, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)

class rideAPI(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            if request.GET.get('id'):
                ride = Ride.objects.filter(id=request.GET.get('id')).first()
                if not ride:
                    return Response({"message": "No data"}, status=status.HTTP_204_NO_CONTENT)
            else:
                user_details = UserDetails.objects.get(user=request.user)
                if user_details.user_type == 'Admin':
                    rides = Ride.objects.all()
                if user_details.user_type == 'Driver':
                    rides = Ride.objects.filter(driver=request.user)
                if user_details.user_type == 'Customer':
                    rides = Ride.objects.filter(rider=request.user)
                if not rides.exists():
                    return Response({"message": "No data"}, status=status.HTTP_204_NO_CONTENT)
                
                serializer = RideSerializer(rides, many=True)
                return Response(serializer.data, status=status.HTTP_200_OK)

            serializer = RideSerializer(ride, many=False)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
    
    def post(self, request):

        try:
            validate_data = request.data
            validate_data['rider_id'] = request.user.id
            validate_data['pickup_location'] = str(request.data.get('pickup_location'))
            validate_data['dropoff_location'] = str(request.data.get('dropoff_location'))
            status_instance = RideStatus.objects.filter(status='Requested').first()
            if status_instance:
                validate_data['status'] = status_instance
            else:
                return Response({'detail': 'Invalid status ID'}, status=status.HTTP_400_BAD_REQUEST)
            Ride.objects.create(**validate_data)
            return Response({'detail': 'ride requested'}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
    
    def put(self, request):
        try:
            if request.data.get('id'):
                user_details = UserDetails.objects.get(user=request.user)
                ride = Ride.objects.get(id = request.data.get('id'))
                if user_details.user_type not in 'Driver' and ride.driver != request.user:
                    raise PermissionDenied("User does not have the privilege")
                if request.data.get('status') == 'Accept' and ride.status.status == "Requested":
                    ride.status = RideStatus.objects.get(status = "Accepted")
                elif request.data.get('status') == 'Start' and ride.status.status == "Accepted":
                    ride.status = RideStatus.objects.get(status = "Started")
                elif request.data.get('status') == 'Completed' and ride.status.status == "Started":
                    ride.status = RideStatus.objects.get(status = "Completed")
                elif request.data.get('status') == 'Cancel' and ride.status.status == "Requested":
                    ride.status = RideStatus.objects.get(status = "Cancelled")
                else:
                    raise Exception("Invalid status transition")
                ride.save()
                return Response({'detail': 'Status updated'}, status=status.HTTP_200_OK)
            return Response({'detail': 'Invalid ID'}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionDenied as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

