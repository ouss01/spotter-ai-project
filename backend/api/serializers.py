from rest_framework import serializers


class PlanTripSerializer(serializers.Serializer):
    current_location = serializers.CharField(max_length=500)
    pickup = serializers.CharField(max_length=500)
    dropoff = serializers.CharField(max_length=500)
    cycle_used_hours = serializers.FloatField(min_value=0.0, max_value=70.0)
    trip_start_iso = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional ISO-8601 datetime for trip start (UTC). Defaults to now.",
    )
