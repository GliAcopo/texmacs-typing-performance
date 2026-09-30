;; Loaded by shift-check.py: puts the cursor at the end of body paragraph TMSHIFT_PAR
;; (or of the first long text paragraph at or after it), binds F12 to a full repaint of
;; the window and C-F12 to a full retypeset of the document, and touches TMSHIFT_READY
;; once TeXmacs is idle.
(define (shift-check-par)
  (let* ((body (buffer-tree))
         (n (tree-arity body))
         (start (min (- n 1) (string->number (or (getenv "TMSHIFT_PAR") "30")))))
    (let loop ((i start))
      (if (>= i n) (tree-ref body start)
          (let ((t (tree-ref body i)))
            (if (or (and (tree-atomic? t) (> (string-length (tree->string t)) 40))
                    (tree-is? t 'concat))
                t
                (loop (+ i 1))))))))

(kbd-map ("F12" (refresh-window))
         ("C-F12" (update-current-buffer)))

(delayed
  (:idle 2000)
  (tree-go-to (shift-check-par) :end)
  (delayed
    (:idle 3000)
    (system (string-append "touch '" (getenv "TMSHIFT_READY") "'"))))
