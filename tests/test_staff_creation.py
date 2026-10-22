from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class StaffCreationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="StrongPassword!2026",
            full_name="Lot Administrator",
            mobile="9876543210",
            role=User.Role.ADMIN,
        )

        self.attendant = User.objects.create_user(
            email="attendant@example.com",
            password="StrongPassword!2026",
            full_name="Gate Attendant",
            mobile="9876543211",
            role=User.Role.ATTENDANT,
        )

        self.url = reverse("accounts:create_staff")

        self.payload = {
            "full_name": "New Staff Member",
            "email": "newstaff@example.com",
            "mobile": "9876543212",
            "password": "AnotherStrongPassword!2026",
            "role": User.Role.ATTENDANT,
        }

    def test_attendant_cannot_create_staff(self):
        self.client.force_login(self.attendant)

        response = self.client.post(self.url, self.payload)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            User.objects.filter(email=self.payload["email"]).exists()
        )

    def test_admin_can_create_gate_attendant(self):
        self.client.force_login(self.admin)

        response = self.client.post(self.url, self.payload)

        self.assertRedirects(response, self.url)
        staff = User.objects.get(email=self.payload["email"])
        self.assertEqual(staff.role, User.Role.ATTENDANT)
        self.assertTrue(staff.check_password(self.payload["password"]))

    def test_admin_can_create_another_administrator(self):
        self.client.force_login(self.admin)
        self.payload["role"] = User.Role.ADMIN

        response = self.client.post(self.url, self.payload)

        self.assertRedirects(response, self.url)
        self.assertTrue(
            User.objects.filter(
                email=self.payload["email"],
                role=User.Role.ADMIN,
            ).exists()
        )

    def test_admin_cannot_create_a_driver_using_staff_form(self):
        self.client.force_login(self.admin)
        self.payload["role"] = User.Role.DRIVER

        response = self.client.post(self.url, self.payload)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            User.objects.filter(email=self.payload["email"]).exists()
        )

    def test_anonymous_user_cannot_create_staff(self):
        response = self.client.post(self.url, self.payload)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            User.objects.filter(email=self.payload["email"]).exists()
        )