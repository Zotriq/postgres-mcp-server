-- Small e-commerce database used by the tests and the README examples.
DROP TABLE IF EXISTS public.order_items, public.orders, public.products, public.customers CASCADE;

CREATE TABLE public.customers (
    id          serial PRIMARY KEY,
    name        text NOT NULL,
    email       text NOT NULL UNIQUE,
    country     text NOT NULL,
    created_at  date NOT NULL DEFAULT current_date
);
COMMENT ON TABLE public.customers IS 'People who have placed at least one order';

CREATE TABLE public.products (
    id        serial PRIMARY KEY,
    name      text NOT NULL,
    category  text NOT NULL,
    price     numeric(10,2) NOT NULL
);

CREATE TABLE public.orders (
    id           serial PRIMARY KEY,
    customer_id  int NOT NULL REFERENCES public.customers(id),
    status       text NOT NULL CHECK (status IN ('pending','paid','shipped','refunded')),
    ordered_at   date NOT NULL
);

CREATE TABLE public.order_items (
    order_id    int NOT NULL REFERENCES public.orders(id),
    product_id  int NOT NULL REFERENCES public.products(id),
    quantity    int NOT NULL,
    PRIMARY KEY (order_id, product_id)
);

INSERT INTO public.customers (name, email, country, created_at) VALUES
  ('Ayesha Khan', 'ayesha@example.com', 'Pakistan', '2026-01-10'),
  ('Liam Smith',  'liam@example.com',   'UK',       '2026-02-03'),
  ('Sofia Rossi', 'sofia@example.com',  'Italy',    '2026-03-21');

INSERT INTO public.products (name, category, price) VALUES
  ('Mechanical Keyboard', 'Accessories', 89.00),
  ('27" Monitor',         'Displays',   249.00),
  ('USB-C Hub',           'Accessories', 39.50);

INSERT INTO public.orders (customer_id, status, ordered_at) VALUES
  (1, 'paid', '2026-04-01'), (1, 'shipped', '2026-05-12'),
  (2, 'paid', '2026-04-18'), (3, 'refunded', '2026-06-02');

INSERT INTO public.order_items VALUES
  (1, 1, 1), (1, 3, 2), (2, 2, 1), (3, 2, 2), (4, 3, 1);
